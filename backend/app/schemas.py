from datetime import date
from pydantic import BaseModel, Field


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)


class AuthUserResponse(BaseModel):
    username: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class GenerateRequest(BaseModel):
    sites: int = Field(default=30, ge=1, le=500)
    deliveries: int = Field(default=100, ge=1, le=2000)
    vehicles: int = Field(default=10, ge=1, le=100)
    seed: int = 20261022
    reference_date: date = Field(default_factory=date.today)


class OptimizeRequest(BaseModel):
    route_date: date = Field(default_factory=date.today)
    time_limit_seconds: int = Field(default=5, ge=1, le=60)

