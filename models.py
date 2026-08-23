# models.py
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class TenderStatus(StrEnum):
    """Processing status of a tender document."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Tender(Base):
    """Uploaded tender document."""

    __tablename__ = "tenders"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    status: Mapped[TenderStatus] = mapped_column(
        Enum(TenderStatus, name="tender_status"),
        nullable=False,
        default=TenderStatus.QUEUED,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    summary: Mapped["TenderSummary | None"] = relationship(
        back_populates="tender",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TenderSummary(Base):
    """LLM-generated summary of a tender document."""

    __tablename__ = "tender_summaries"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    contract_amount: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    execution_period: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    requirements: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    penalties: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    raw_llm_response: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    tender: Mapped["Tender"] = relationship(
        back_populates="summary",
    )