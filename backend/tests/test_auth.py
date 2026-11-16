import unittest
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        test_session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        def override_get_db():
            db = test_session()
            try:
                yield db
            finally:
                db.close()

        self.original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def test_lifespan(_app):
            yield

        app.router.lifespan_context = test_lifespan
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.router.lifespan_context = self.original_lifespan
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_registration_login_and_logout(self):
        credentials = {"username": "warehouse_user", "password": "secure-password-123"}
        response = self.client.post("/api/v1/auth/register", json=credentials)
        self.assertEqual(response.status_code, 201)
        registered = response.json()
        self.assertEqual(registered["user"]["role"], "carrier_warehouse_operator")
        self.assertNotIn("password", registered)

        token = registered["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/sites", headers=headers).status_code, 200)

        bad_login = self.client.post(
            "/api/v1/auth/login",
            json={"username": credentials["username"], "password": "wrong-password-123"},
        )
        self.assertEqual(bad_login.status_code, 401)

        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 401)

    def test_duplicate_user_and_anonymous_access_are_rejected(self):
        credentials = {"username": "delivery_user", "password": "secure-password-456"}
        self.assertEqual(self.client.post("/api/v1/auth/register", json=credentials).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/register", json=credentials).status_code, 409)
        self.assertEqual(self.client.get("/api/v1/sites").status_code, 401)


if __name__ == "__main__":
    unittest.main()
