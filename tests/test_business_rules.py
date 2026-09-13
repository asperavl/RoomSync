import pytest
from datetime import datetime, timezone, timedelta
from backend.app.validation import (
    validate_booking_notice,
    validate_cancellation_window,
    validate_time_ordering,
    BusinessRuleViolation,
)
from backend.app.schemas import BookingCreate


class TestBusinessRulesUnit:
    """
    Business rule unit tests for RoomSync operational policies.
    Tested with pytest-cov to measure overall coverage on booking validation logic.
    """

    def test_booking_within_min_notice_period_rejected(self):
        """Booking attempted within a resource's min_notice_minutes -> assert rejection."""
        now = datetime.now(timezone.utc)
        # Booking starts in 10 minutes, but resource requires 30 minutes notice
        start_time = now + timedelta(minutes=10)

        with pytest.raises(BusinessRuleViolation) as exc_info:
            validate_booking_notice(
                start_time=start_time,
                min_notice_minutes=30,
                reference_time=now,
            )

        assert exc_info.value.rule_name == "min_notice_period"
        assert "insufficient notice" in exc_info.value.message.lower()

    def test_booking_outside_notice_period_succeeds(self):
        """Booking attempted outside the notice period -> assert success."""
        now = datetime.now(timezone.utc)
        # Booking starts in 45 minutes, resource requires 30 minutes notice
        start_time = now + timedelta(minutes=45)

        # Should not raise any exception
        validate_booking_notice(
            start_time=start_time,
            min_notice_minutes=30,
            reference_time=now,
        )

    def test_cancellation_within_cancellation_window_rejected(self):
        """Cancellation attempted within cancellation_window_minutes -> assert rejection."""
        now = datetime.now(timezone.utc)
        # Meeting starts in 10 minutes, but cancellation window is 15 minutes
        booking_start = now + timedelta(minutes=10)

        with pytest.raises(BusinessRuleViolation) as exc_info:
            validate_cancellation_window(
                start_time=booking_start,
                cancellation_window_minutes=15,
                reference_time=now,
            )

        assert exc_info.value.rule_name == "cancellation_window_exceeded"
        assert "cancellation rejected" in exc_info.value.message.lower()

    def test_cancellation_outside_window_succeeds(self):
        """Cancellation attempted outside the window -> assert success."""
        now = datetime.now(timezone.utc)
        # Meeting starts in 60 minutes, cancellation window is 15 minutes
        booking_start = now + timedelta(minutes=60)

        # Should not raise any exception
        validate_cancellation_window(
            start_time=booking_start,
            cancellation_window_minutes=15,
            reference_time=now,
        )

    def test_cancellation_of_past_booking_rejected(self):
        """Cannot cancel a meeting that is already in-progress or completed."""
        now = datetime.now(timezone.utc)
        past_start = now - timedelta(minutes=5)

        with pytest.raises(BusinessRuleViolation) as exc_info:
            validate_cancellation_window(
                start_time=past_start,
                cancellation_window_minutes=15,
                reference_time=now,
            )

        assert exc_info.value.rule_name == "cancellation_past_booking"

    def test_booking_with_end_time_before_or_equal_to_start_rejected(self):
        """Booking with end_time <= start_time -> assert rejection."""
        now = datetime.now(timezone.utc)
        start = now + timedelta(hours=2)
        end_equal = start
        end_before = start - timedelta(minutes=30)

        # 1. Validation function level
        with pytest.raises(BusinessRuleViolation):
            validate_time_ordering(start, end_equal)

        with pytest.raises(BusinessRuleViolation):
            validate_time_ordering(start, end_before)

        # 2. Pydantic schema model validator level
        with pytest.raises(ValueError):
            BookingCreate(
                resource_id=1,
                user_id=1,
                start_time=start,
                end_time=end_equal,
            )

        with pytest.raises(ValueError):
            BookingCreate(
                resource_id=1,
                user_id=1,
                start_time=start,
                end_time=end_before,
            )

    def test_valid_time_ordering_succeeds(self):
        """Valid start and end times succeed."""
        now = datetime.now(timezone.utc)
        start = now + timedelta(hours=2)
        end = start + timedelta(hours=1)

        validate_time_ordering(start, end)
        schema = BookingCreate(
            resource_id=1,
            user_id=1,
            start_time=start,
            end_time=end,
        )
        assert schema.start_time == start
        assert schema.end_time == end
