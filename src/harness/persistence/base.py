"""Declarative base for all persistence ORM models (research R1).

A single shared ``Base`` carries the ``MetaData`` that every entity model and
the Alembic migration chain register against.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared SQLAlchemy 2.0 declarative base for all harness entities."""
