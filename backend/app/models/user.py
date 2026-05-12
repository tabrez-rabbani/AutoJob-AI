"""
AutoJob AI — User Model
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SubscriptionTier(str, PyEnum):
    FREE = "free"
    PRO = "pro"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Profile
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    preferred_roles: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    preferred_locations: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    preferred_country: Mapped[str | None] = mapped_column(String(100), nullable=True, default="India")
    min_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    current_ctc: Mapped[float | None] = mapped_column(Float, nullable=True, default=0)
    expected_ctc: Mapped[float | None] = mapped_column(Float, nullable=True, default=0)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    current_city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Contact info (extracted from resume)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # LinkedIn credentials (AES-256 encrypted)
    linkedin_email_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_password_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # SMTP credentials for email apply (AES-256 encrypted)
    smtp_email_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_password_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True, default="smtp.gmail.com")
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=587)

    # Naukri.com credentials (AES-256 encrypted)
    naukri_email_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    naukri_password_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Account
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    subscription_tier: Mapped[str] = mapped_column(
        String(20), default=SubscriptionTier.FREE.value
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    applications = relationship("Application", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
