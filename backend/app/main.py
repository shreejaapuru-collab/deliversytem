from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session, joinedload

from app.core.auth import (
    Role,
    allow,
    create_login_session,
    current_login_session,
    current_user,
    ensure_bootstrap_admin,
    hash_password,
    verify_password,
)
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.roles import ANALYTICS_OPERATIONS, DATA_ADMIN_OPERATIONS, FLEET_OPERATIONS, PLANNING_OPERATIONS, READ_OPERATIONS
from app import models
from app.models import Delivery, Driver, LoginSession, Outcome, Route, RouteStop, Site, User, Vehicle
from app.schemas import AuthCredentials, AuthResponse, AuthUserResponse, GenerateRequest, OptimizeRequest
from app.services.generator import generate_data
from app.services.optimizer import optimize
from app.services.simulation import simulate
from app.services.data_quality import export_delivery_csv, export_json, validate_data

Base.metadata.create_all(bind=engine)

# Add the human-readable stop ID to databases created by earlier versions.
if "route_stops" in inspect(engine).get_table_names():
    route_stop_columns = {column["name"] for column in inspect(engine).get_columns("route_stops")}
    if "stop_code" not in route_stop_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE route_stops ADD COLUMN stop_code VARCHAR(64)"))
            legacy_stops = connection.execute(
                text("SELECT id, route_id, sequence FROM route_stops WHERE stop_code IS NULL")
            ).mappings().all()
            for stop in legacy_stops:
                code = f"STOP-{stop['route_id']}-{stop['sequence']:03d}"
                connection.execute(
                    text("UPDATE route_stops SET stop_code = :code WHERE id = :id"),
                    {"code": code, "id": stop["id"]},
                )
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_route_stops_stop_code ON route_stops (stop_code)"
            ))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        ensure_bootstrap_admin(db)
    yield


app = FastAPI(
    title="Smart Delivery Operations API",
    version="1.0.0",
    description="Synthetic delivery planning and operations API",
    docs_url="/api/v1/docs",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


@app.get("/")
def root():
    return {"message": "Smart Delivery Operations API", "docs": "/api/v1/docs"}


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(credentials: AuthCredentials, db: Session = Depends(get_db)):
    username = credentials.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "That username is already registered")
    user = User(
        username=username,
        password_hash=hash_password(credentials.password),
        role=Role.CARRIER.value,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "That username is already registered") from exc
    db.refresh(user)
    token = create_login_session(db, user)
    return AuthResponse(
        access_token=token,
        user=AuthUserResponse(username=user.username, role=user.role),
    )


@app.post("/api/v1/auth/login", response_model=AuthResponse)
def login(credentials: AuthCredentials, db: Session = Depends(get_db)):
    username = credentials.username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    token = create_login_session(db, user)
    return AuthResponse(
        access_token=token,
        user=AuthUserResponse(username=user.username, role=user.role),
    )


@app.get("/api/v1/auth/me", response_model=AuthUserResponse)
def get_signed_in_user(user: User = Depends(current_user)):
    return AuthUserResponse(username=user.username, role=user.role)


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(login_session: LoginSession = Depends(current_login_session), db: Session = Depends(get_db)):
    db.delete(login_session)
    db.commit()


@app.post("/api/v1/data/generate", dependencies=[Depends(allow(*DATA_ADMIN_OPERATIONS))])
def create_data(request: GenerateRequest, db: Session = Depends(get_db)):
    try:
        return generate_data(db, request)
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/v1/data/validate", dependencies=[Depends(allow(*DATA_ADMIN_OPERATIONS))])
def data_validation(db: Session = Depends(get_db)):
    return validate_data(db)


@app.get("/api/v1/data/export.json", dependencies=[Depends(allow(*DATA_ADMIN_OPERATIONS))])
def data_export_json(db: Session = Depends(get_db)):
    return export_json(db)


@app.get("/api/v1/data/export.csv", dependencies=[Depends(allow(*DATA_ADMIN_OPERATIONS))])
def data_export_csv(db: Session = Depends(get_db)):
    return Response(export_delivery_csv(db), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=deliveries.csv"})


@app.get("/api/v1/sites", dependencies=[Depends(allow(*READ_OPERATIONS))])
def list_sites(q: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(Site)
    if q:
        query = query.filter(Site.name.ilike(f"%{q}%"))
    total = query.count()
    return {"items": query.order_by(Site.site_code).offset(offset).limit(limit).all(), "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/deliveries", dependencies=[Depends(allow(*READ_OPERATIONS))])
def list_deliveries(status: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(Delivery)
    if status:
        query = query.filter(Delivery.status == status.upper())
    return {"items": query.order_by(Delivery.id).offset(offset).limit(limit).all(), "total": query.count(), "limit": limit, "offset": offset}


@app.get("/api/v1/vehicles", dependencies=[Depends(allow(*FLEET_OPERATIONS))])
def list_vehicles(db: Session = Depends(get_db)):
    return db.query(Vehicle).order_by(Vehicle.id).all()


@app.get("/api/v1/drivers", dependencies=[Depends(allow(*FLEET_OPERATIONS))])
def list_drivers(db: Session = Depends(get_db)):
    return db.query(Driver).order_by(Driver.id).all()


@app.post("/api/v1/optimization/run", dependencies=[Depends(allow(*PLANNING_OPERATIONS))])
def run_optimization(request: OptimizeRequest, db: Session = Depends(get_db)):
    try:
        return optimize(db, request.route_date, request.time_limit_seconds)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/routes", dependencies=[Depends(allow(*READ_OPERATIONS))])
def list_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.route_date.desc(), Route.id).all()


@app.get("/api/v1/routes/{route_id}", dependencies=[Depends(allow(*READ_OPERATIONS))])
def route_details(route_id: str, db: Session = Depends(get_db)):
    route = db.query(Route).options(joinedload(Route.stops).joinedload(RouteStop.delivery)).filter_by(id=route_id).first()
    if route is None:
        raise HTTPException(404, "Route not found")
    return route


@app.post("/api/v1/simulation/{route_id}/run", dependencies=[Depends(allow(*FLEET_OPERATIONS))])
def run_simulation(route_id: str, db: Session = Depends(get_db)):
    try:
        return simulate(db, route_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/v1/dashboard/summary", dependencies=[Depends(allow(*ANALYTICS_OPERATIONS))])
@app.get("/api/v1/analytics/summary", dependencies=[Depends(allow(*ANALYTICS_OPERATIONS))])
def analytics(db: Session = Depends(get_db)):
    total = db.query(Delivery).count()
    completed = db.query(Outcome).filter(Outcome.status.in_(["DELIVERED", "DELAYED"])).count()
    failed = db.query(Outcome).filter(Outcome.status == "FAILED").count()
    on_time = db.query(Outcome).filter(Outcome.status == "DELIVERED").count()
    avg_delay = db.query(func.avg(Outcome.delay_minutes)).scalar() or 0
    return {"total_deliveries": total, "successful_deliveries": completed, "failed_deliveries": failed,
            "unassigned_deliveries": db.query(Delivery).filter(Delivery.status == "UNASSIGNED").count(),
            "on_time_rate_percent": round(on_time / completed * 100, 1) if completed else 0,
            "average_delay_minutes": round(float(avg_delay), 1), "routes": db.query(Route).count(),
            "vehicles": db.query(Vehicle).count()}

