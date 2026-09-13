from datetime import datetime, timezone, timedelta
from typing import Optional


class BusinessRuleViolation(Exception):
    """Exception raised when an operational business rule is violated."""
    def __init__(self, message: str, rule_name: str):
        super().__init__(message)
        self.message = message
        self.rule_name = rule_name


def ensure_timezone_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def validate_time_ordering(start_time: datetime, end_time: datetime) -> None:
    """Rejects if end_time is not strictly greater than start_time."""
    if end_time <= start_time:
        raise BusinessRuleViolation(
            message="end_time must be strictly greater than start_time",
            rule_name="time_ordering"
        )


def validate_booking_notice(
    start_time: datetime,
    min_notice_minutes: int,
    reference_time: Optional[datetime] = None,
) -> None:
    """
    Ensures that a booking is attempted outside the minimum notice period.
    Rejects if start_time - reference_time < min_notice_minutes.
    """
    now = ensure_timezone_aware(reference_time or datetime.now(timezone.utc))
    start = ensure_timezone_aware(start_time)

    required_earliest_start = now + timedelta(minutes=min_notice_minutes)
    if start < required_earliest_start:
        remaining_minutes = int((start - now).total_seconds() / 60)
        raise BusinessRuleViolation(
            message=(
                f"Booking attempted with insufficient notice ({remaining_minutes} mins). "
                f"This resource requires at least {min_notice_minutes} minutes notice."
            ),
            rule_name="min_notice_period"
        )


def validate_cancellation_window(
    start_time: datetime,
    cancellation_window_minutes: int,
    reference_time: Optional[datetime] = None,
) -> None:
    """
    Ensures that cancellation is attempted outside the restricted cancellation window.
    Rejects if start_time - reference_time < cancellation_window_minutes.
    """
    now = ensure_timezone_aware(reference_time or datetime.now(timezone.utc))
    start = ensure_timezone_aware(start_time)

    if start <= now:
        raise BusinessRuleViolation(
            message="Cannot cancel a booking that is already in progress or completed.",
            rule_name="cancellation_past_booking"
        )

    restricted_deadline = start - timedelta(minutes=cancellation_window_minutes)
    if now > restricted_deadline:
        diff_minutes = int((start - now).total_seconds() / 60)
        raise BusinessRuleViolation(
            message=(
                f"Cancellation rejected: only {diff_minutes} minutes remain before start. "
                f"Cancellations must be made at least {cancellation_window_minutes} minutes in advance."
            ),
            rule_name="cancellation_window_exceeded"
        )
