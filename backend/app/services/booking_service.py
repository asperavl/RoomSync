import asyncio
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError

from backend.app.models import Booking, Resource, BookingAuditLog
from backend.app.schemas import BookingCreate
from backend.app.validation import (
    validate_time_ordering,
    validate_booking_notice,
    validate_cancellation_window,
    BusinessRuleViolation,
)


class BookingConflictError(Exception):
    """Raised when an overlapping booking exists for the same resource."""
    def __init__(self, message: str = "Resource is already booked for the selected time slot."):
        super().__init__(message)
        self.message = message


class ResourceNotFoundError(Exception):
    pass


class BookingNotFoundError(Exception):
    pass


async def create_booking_constraint_protected(
    session: AsyncSession,
    data: BookingCreate,
    reference_time: Optional[datetime] = None,
) -> Booking:
    """
    Creates a booking relying on the PostgreSQL GiST exclusion constraint.
    Validates operational rules in application code, but delegates concurrency & overlap
    guarantees directly to the database storage engine.
    """
    # 1. Validate time ordering
    validate_time_ordering(data.start_time, data.end_time)

    # 2. Fetch resource to inspect operational rules
    res_result = await session.execute(
        select(Resource).where(Resource.id == data.resource_id)
    )
    resource = res_result.scalar_one_or_none()
    if not resource:
        raise ResourceNotFoundError(f"Resource {data.resource_id} not found")

    # 3. Validate notice period rule
    validate_booking_notice(
        start_time=data.start_time,
        min_notice_minutes=resource.min_notice_minutes,
        reference_time=reference_time,
    )

    # 4. Insert booking inside transaction
    booking = Booking(
        resource_id=data.resource_id,
        user_id=data.user_id,
        start_time=data.start_time,
        end_time=data.end_time,
        title=data.title or "Room Reservation",
        status="confirmed",
    )
    session.add(booking)

    try:
        await session.flush()
    except (IntegrityError, OperationalError, DBAPIError) as exc:
        await session.rollback()
        # In PostgreSQL, 23P01 is exclusion_violation, 40P01 is deadlock
        # We catch any integrity or concurrency lock conflict on overlap and raise conflict
        raise BookingConflictError("Overlapping booking exists for this resource.") from exc

    # 5. Record audit log
    audit = BookingAuditLog(
        booking_id=booking.id,
        action="created",
        detail=f"Reserved slot [{data.start_time} - {data.end_time}] via constraint-protected flow",
    )
    session.add(audit)
    await session.commit()
    await session.refresh(booking)
    return booking


async def create_booking_naive_check_then_insert(
    session: AsyncSession,
    data: BookingCreate,
    simulate_delay: float = 0.05,
) -> Booking:
    """
    Naive implementation: checks for overlaps with a plain SELECT,
    then performs an INSERT without locking or exclusion constraint.
    Intentionally exposes the classic TOCTOU race condition under concurrency.
    """
    validate_time_ordering(data.start_time, data.end_time)

    # 1. Plain SELECT for overlapping confirmed bookings
    # Overlap condition: start < new_end AND end > new_start
    query = select(Booking).where(
        and_(
            Booking.resource_id == data.resource_id,
            Booking.status == "confirmed",
            Booking.start_time < data.end_time,
            Booking.end_time > data.start_time,
        )
    )
    result = await session.execute(query)
    conflicts = result.scalars().all()

    if conflicts:
        raise BookingConflictError("Naive check: Slot already booked.")

    # Artificial micro-yield simulating async network/IO processing between check and insert
    if simulate_delay > 0:
        await asyncio.sleep(simulate_delay)

    # 2. Insert without locking
    booking = Booking(
        resource_id=data.resource_id,
        user_id=data.user_id,
        start_time=data.start_time,
        end_time=data.end_time,
        status="confirmed",
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking


async def cancel_booking(
    session: AsyncSession,
    booking_id: int,
    user_id: int,
    reference_time: Optional[datetime] = None,
    reason: Optional[str] = None,
) -> Booking:
    """
    Cancels an existing booking while enforcing the cancellation window rule.
    """
    result = await session.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise BookingNotFoundError(f"Booking {booking_id} not found")

    if booking.status == "cancelled":
        return booking

    # Load resource for cancellation window rule
    res_result = await session.execute(
        select(Resource).where(Resource.id == booking.resource_id)
    )
    resource = res_result.scalar_one_or_none()
    window_minutes = resource.cancellation_window_minutes if resource else 15

    # Enforce rule
    validate_cancellation_window(
        start_time=booking.start_time,
        cancellation_window_minutes=window_minutes,
        reference_time=reference_time,
    )

    booking.status = "cancelled"
    audit = BookingAuditLog(
        booking_id=booking.id,
        action="cancelled",
        detail=f"Cancelled by user {user_id}. Reason: {reason or 'Not specified'}",
    )
    session.add(audit)
    await session.commit()
    await session.refresh(booking)
    return booking
