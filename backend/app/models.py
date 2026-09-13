from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from backend.app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False, index=True)
    google_refresh_token = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    capacity = Column(Integer, nullable=True)
    min_notice_minutes = Column(Integer, nullable=False, default=30)
    cancellation_window_minutes = Column(Integer, nullable=False, default=15)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    bookings = relationship("Booking", back_populates="resource", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("type IN ('room', 'equipment')", name="check_resource_type"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    title = Column(Text, nullable=True, default="Room Reservation")
    google_event_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="confirmed")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    resource = relationship("Resource", back_populates="bookings")
    user = relationship("User", back_populates="bookings")
    audit_logs = relationship("BookingAuditLog", back_populates="booking", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="check_end_after_start"),
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'conflict_flagged', 'sync_failed')",
            name="check_booking_status",
        ),
        # Core PostgreSQL exclusion constraint preventing overlapping active bookings
        ExcludeConstraint(
            ("resource_id", "="),
            (func.tstzrange(Column("start_time"), Column("end_time")), "&&"),
            where="status = 'confirmed'",
            using="gist",
            name="no_overlapping_bookings",
        ),
        Index("idx_bookings_resource_time", "resource_id", "start_time", "end_time"),
        Index("idx_bookings_user", "user_id"),
    )


class BookingAuditLog(Base):
    __tablename__ = "booking_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    action = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    booking = relationship("Booking", back_populates="audit_logs")
