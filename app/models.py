"""ORM models for user-submitted data."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class _Row:
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Lead(_Row, Base):
    __tablename__ = "leads"

    course_id: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)


class Listing(_Row, Base):
    __tablename__ = "listings"

    business_name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)


class Correction(_Row, Base):
    __tablename__ = "corrections"

    provider_id: Mapped[str] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(Text)


class Carousel(_Row, Base):
    __tablename__ = "carousels"

    idea: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
