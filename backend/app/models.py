from datetime import date, datetime, time, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    region: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    orders: Mapped[list["Order"]] = relationship(back_populates="site")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    order_date: Mapped[date] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    site: Mapped[Site] = relationship(back_populates="orders")
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    weight: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    service_minutes: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")
    status: Mapped[str] = mapped_column(String(24), default="UNASSIGNED")
    earliest: Mapped[time] = mapped_column(Time, default=time(9, 0))
    latest: Mapped[time] = mapped_column(Time, default=time(17, 0))
    order: Mapped[Order] = relationship(back_populates="deliveries")
    site: Mapped[Site] = relationship()


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(32))
    weight_capacity: Mapped[float] = mapped_column(Float)
    volume_capacity: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    shift_date: Mapped[date] = mapped_column(Date)
    starts: Mapped[time] = mapped_column(Time)
    ends: Mapped[time] = mapped_column(Time)
    max_minutes: Mapped[int] = mapped_column(Integer, default=480)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    route_date: Mapped[date] = mapped_column(Date)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    status: Mapped[str] = mapped_column(String(24), default="PLANNED")
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete-orphan", order_by="RouteStop.sequence")


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (UniqueConstraint("route_id", "sequence", name="uq_route_sequence"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), index=True)
    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    planned_arrival: Mapped[datetime] = mapped_column(DateTime)
    route: Mapped[Route] = relationship(back_populates="stops")
    delivery: Mapped[Delivery] = relationship()


class Outcome(Base):
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.id"), unique=True, index=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)


class OutcomeEvent(Base):
    """Append-only record of each simulation result."""
    __tablename__ = "outcome_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # IDs are snapshots, so old events survive replacement of a generated dataset.
    delivery_id: Mapped[str] = mapped_column(String(32), index=True)
    route_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class GroundTruth(Base):
    """Labels for deliberately generated exceptions; keep separate from planner inputs."""
    __tablename__ = "ground_truth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    issue_type: Mapped[str] = mapped_column(String(64))
    expected_decision: Mapped[str] = mapped_column(String(120))


class TravelTimeMatrix(Base):
    __tablename__ = "travel_time_matrix"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_date: Mapped[date] = mapped_column(Date, index=True)
    # A null origin represents the synthetic depot.
    from_site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True, index=True)
    to_site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    travel_minutes: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(24), default="NORMAL")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="carrier_warehouse_operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    sessions: Mapped[list["LoginSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user: Mapped[User] = relationship(back_populates="sessions")

