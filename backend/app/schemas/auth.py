"""
AutoJob AI — Auth Schemas
Pydantic models for authentication API requests and responses.
"""

from pydantic import BaseModel, Field, EmailStr


class SignupRequest(BaseModel):
    """User registration request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password (min 8 chars)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Full name")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
                "full_name": "Sohan Kumar",
            }
        }
    }


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
            }
        }
    }


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback — frontend sends the authorization code."""
    code: str = Field(..., description="Google authorization code from OAuth redirect")
    redirect_uri: str = Field(..., description="OAuth redirect URI used by frontend")


class TokenResponse(BaseModel):
    """JWT token response after login/signup."""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    """Public user profile data."""
    id: str
    email: str
    full_name: str
    resume_url: str | None = None
    skills: list[str] | None = None
    preferred_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    preferred_country: str | None = None
    experience_years: int | None = None
    current_ctc: float | None = None
    expected_ctc: float | None = None
    notice_period_days: int | None = None
    current_city: str | None = None
    subscription_tier: str = "free"
    # SMTP (never expose password)
    smtp_email: str | None = None
    smtp_configured: bool = False
    smtp_host: str | None = None
    smtp_port: int | None = None
    # Naukri (never expose password)
    naukri_email: str | None = None
    naukri_configured: bool = False
    # LinkedIn (never expose password)
    linkedin_email: str | None = None
    linkedin_configured: bool = False

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    """Update user profile fields."""
    full_name: str | None = None
    skills: list[str] | None = None
    preferred_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    preferred_country: str | None = None
    experience_years: int | None = None
    current_ctc: float | None = None
    expected_ctc: float | None = None
    notice_period_days: int | None = None
    current_city: str | None = None
    # Contact info (from resume or manual)
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    # SMTP settings
    smtp_email: str | None = None
    smtp_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    # Naukri.com credentials
    naukri_email: str | None = None
    naukri_password: str | None = None
    # LinkedIn credentials
    linkedin_email: str | None = None
    linkedin_password: str | None = None
