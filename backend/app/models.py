import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EmailCapture(Base):
    __tablename__ = "email_captures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    tool_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="email_capture")


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_capture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_captures.id"), nullable=False
    )
    tool_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_phase: Mapped[str | None] = mapped_column(String(30), nullable=True)
    phase_progress: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    input_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    email_capture: Mapped["EmailCapture"] = relationship("EmailCapture", back_populates="jobs")
    results: Mapped[list["JobResult"]] = relationship(
        "JobResult", back_populates="job", cascade="all, delete-orphan"
    )


class JobResult(Base):
    __tablename__ = "job_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    search_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_domain: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_domain: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contacts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="results")


class RateLimit(Base):
    __tablename__ = "rate_limits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
