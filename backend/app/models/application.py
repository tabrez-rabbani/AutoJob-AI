"""
AutoJob AI — Application Model (tracks job applications)
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApplicationStatus(str, PyEnum):
    QUEUED = "queued"          # Job matched, waiting to apply
    APPLYING = "applying"      # Currently being processed
    APPLIED = "applied"        # Successfully applied
    EMAILED = "emailed"        # Applied via email (feed scanner)
    EXTERNAL_APPLY = "external_apply"  # No Easy Apply — needs manual application
    SKIPPED = "skipped"        # Complex form, skipped
    INTERVIEW = "interview"    # Got interview
    REJECTED = "rejected"      # Rejected
    OFFER = "offer"            # Got offer
    FAILED = "failed"          # Application attempt failed


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Application details
    status: Mapped[str] = mapped_column(
        String(20), default=ApplicationStatus.QUEUED.value, index=True
    )
    apply_method: Mapped[str] = mapped_column(
        String(20), default="easy_apply", nullable=False
    )  # "easy_apply", "external_apply", "email"
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tailored_resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tracking
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")

    def __repr__(self) -> str:
        return f"<Application {self.id} status={self.status}>"
