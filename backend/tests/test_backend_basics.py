from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.database import Base
from app.core.auth import Role, allow, current_login_session, ensure_bootstrap_admin, hash_password, verify_password
from app.models import Delivery, Order, User
from app.schemas import GenerateRequest
from app.services.generator import generate_data


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
