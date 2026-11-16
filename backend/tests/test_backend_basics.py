import csv
import io
import zipfile
from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.database import Base
from app.core.auth import Role, allow, current_login_session, ensure_bootstrap_admin, hash_password, verify_password
from app.models import (
    Delivery,
    Driver,
    GroundTruth,
    GroundTruthFixture,
    Order,
    OutcomeEvent,
    RouteStop,
    Shift,
    Site,
    TimeWindow,
    TravelTimeMatrix,
    User,
    Vehicle,
    VehicleCapacity,
)
from app.schemas import GenerateRequest
from app.services.data_quality import (
    export_csv_zip,
    export_json,
    export_sql,
    validate_data,
)
from app.services.generator import generate_data
from app.services.optimizer import optimize
from app.services.simulation import simulate


def test_passwords_are_hashed_and_verified():
    encoded = hash_password("secure-password-123")
    assert encoded != "secure-password-123"
    assert verify_password("secure-password-123", encoded)
    assert not verify_password("wrong-password-123", encoded)


def test_authenticated_account_role_controls_permissions():
    carrier = User(username="carrier", password_hash="unused", role=Role.CARRIER.value)
    assert allow(Role.CARRIER)(carrier) is carrier
    try:
        allow(Role.MANAGER)(carrier)
        assert False, "carrier accounts must not have manager permissions"
    except HTTPException as error:
        assert error.status_code == 403


def test_invalid_session_token_is_rejected():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        try:
            current_login_session("Bearer invalid-token", db)
            assert False, "invalid sessions should be rejected"
        except HTTPException as error:
            assert error.status_code == 401


def test_bootstrap_admin_is_created_from_environment(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "delivery-admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "secure-admin-password-123")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ensure_bootstrap_admin(db)
        admin = db.query(User).filter_by(username="delivery-admin").one()
        assert admin.role == Role.MANAGER.value
        assert verify_password("secure-admin-password-123", admin.password_hash)
        ensure_bootstrap_admin(db)
        assert db.query(User).filter_by(role=Role.MANAGER.value).count() == 1


def test_generator_creates_linked_records_with_requested_counts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        counts = generate_data(db, GenerateRequest(sites=3, deliveries=7, vehicles=2, seed=15))
        assert counts["sites"] == 3
        assert counts["deliveries"] == 7
        assert db.query(Delivery).count() == 7
        assert db.query(Order).count() == 7


def test_generator_creates_reproducible_matrix_and_isolated_ground_truth():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = GenerateRequest(
        sites=3,
        deliveries=7,
        vehicles=2,
        seed=15,
        reference_date=date(2026, 10, 22),
    )
    with Session(engine) as db:
        first = generate_data(db, request)
        report = validate_data(db)
        assert first["sites"] == 3
        assert first["vehicle_capacities"] == 2
        assert first["time_windows"] == 7
        assert first["travel_time_rows"] == 96
        assert first["ground_truth_fixtures"] == 5
        assert db.query(GroundTruth).count() == 2
        assert db.query(GroundTruthFixture).count() == 5
        assert report["valid"]
        assert report["warning_count"] == 1

        second = generate_data(db, request)
        assert second["checksum_sha256"] == first["checksum_sha256"]


def test_optimizer_uses_matrix_and_simulation_records_actual_arrivals():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    reference_date = date(2026, 10, 22)
    with Session(engine) as db:
        site = Site(
            site_code="SITE-0001",
            name="Sample",
            address="1 Main Street",
            latitude=12.9,
            longitude=77.6,
            region="Bengaluru",
        )
        db.add(site)
        db.flush()
        db.add_all(
            [
                Order(id="ORD-2026-000001", site_id=site.id, order_date=reference_date),
                Vehicle(
                    id="VEH-000001",
                    vehicle_type="VAN",
                    weight_capacity=100,
                    volume_capacity=10,
                    latitude=12.9716,
                    longitude=77.5946,
                ),
                Driver(id="DRV-000001", name="Driver"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Delivery(
                    id="DEL-2026-000001",
                    order_id="ORD-2026-000001",
                    site_id=site.id,
                    weight=10,
                    volume=1,
                    service_minutes=10,
                    earliest=time(8),
                    latest=time(18),
                ),
                Shift(
                    driver_id="DRV-000001",
                    shift_date=reference_date,
                    starts=time(8),
                    ends=time(18),
                    max_minutes=480,
                ),
                TimeWindow(
                    delivery_id="DEL-2026-000001",
                    starts_at=time(8),
                    ends_at=time(18),
                    effective_from=reference_date,
                ),
                VehicleCapacity(
                    vehicle_id="VEH-000001",
                    effective_from=reference_date,
                    weight_capacity_kg=100,
                    volume_capacity_m3=10,
                ),
                TravelTimeMatrix(
                    scenario_date=reference_date,
                    from_site_id=None,
                    to_site_id=site.id,
                    travel_minutes=45,
                    scenario="BUSY",
                ),
            ]
        )
        db.commit()

        result = optimize(db, reference_date, 2)
        assert result["assigned"] == 1
        stop = db.query(RouteStop).one()
        assert stop.planned_arrival.hour == 8
        assert stop.planned_arrival.minute == 45

        simulation_result = simulate(db, stop.route_id)
        assert simulation_result["results"][0]["actual_arrival"]
        event = db.query(OutcomeEvent).one()
        assert event.actual_arrival is not None
        assert event.actual_departure > event.actual_arrival


def test_export_formats_keep_ground_truth_separate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        generate_data(
            db,
            GenerateRequest(
                sites=3,
                deliveries=7,
                vehicles=2,
                seed=15,
                reference_date=date(2026, 10, 22),
            ),
        )
        payload = export_json(db)
        assert payload["ground_truth"]["labels"]
        assert payload["manifest"]["checksum_sha256"]
        assert "ground_truth" not in payload["deliveries"][0]

        with zipfile.ZipFile(io.BytesIO(export_csv_zip(db))) as archive:
            assert "deliveries.csv" in archive.namelist()
            assert "ground_truth.csv" in archive.namelist()
            assert "ground_truth_fixtures.csv" in archive.namelist()
            with archive.open("ground_truth.csv") as handle:
                rows = list(csv.reader(io.TextIOWrapper(handle, encoding="utf-8")))
                assert len(rows) > 1

        sql_export = export_sql(db)
        assert "CREATE TABLE IF NOT EXISTS" in sql_export
        assert "INSERT INTO sites (" in sql_export
        assert "login_sessions" not in sql_export
