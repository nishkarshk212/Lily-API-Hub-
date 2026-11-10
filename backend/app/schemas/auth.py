"""Authentication, profile, and support schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    company: str = Field(default="", max_length=120)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Password must include at least one letter and one number.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Password must include at least one letter and one number.")
        return v


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    company: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = Field(default=None, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Password must include at least one letter and one number.")
        return v


class SupportTicketRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=4000)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    company: str
    phone: str
    avatar_url: str
    role: str
    is_email_verified: bool
    is_active: bool
    is_suspended: bool
    suspension_reason: Optional[str] = None
    auth_provider: str
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

