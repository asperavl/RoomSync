import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta
from backend.app.models import Booking
from backend.app.services.google_sync import (
    sync_single_booking_with_retry,
    sync_pending_bookings,
    GoogleCalendarClient,
    GoogleCalendarAPIError,
)


@pytest.mark.asyncio
class TestCalendarSyncUnit:
    """
    Mocked Google Calendar sync tests.
    Tests event creation, exponential backoff retries, and failure states.
    """

    async def test_successful_event_creation_stores_google_event_id(
        self, db_session, sample_resource, sample_user
    ):
        """Successful event creation correctly stores google_event_id on the booking."""
        start = datetime.now(timezone.utc) + timedelta(days=1)
        end = start + timedelta(hours=1)

        booking = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
            google_event_id=None,
        )
        db_session.add(booking)
        await db_session.commit()
        await db_session.refresh(booking)

        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.return_value = {
            "id": "gcal_event_real_12345",
            "status": "confirmed",
        }

        success = await sync_single_booking_with_retry(
            session=db_session,
            booking=booking,
            client=mock_client,
            max_retries=3,
            initial_delay=0.01,
        )

        assert success is True
        assert booking.google_event_id == "gcal_event_real_12345"
        assert booking.status == "confirmed"
        mock_client.create_event.assert_awaited_once()

    async def test_simulated_api_failure_triggers_retry_logic(
        self, db_session, sample_resource, sample_user
    ):
        """A transient API failure (e.g. 503 Service Unavailable) triggers retries and recovers."""
        start = datetime.now(timezone.utc) + timedelta(days=2)
        end = start + timedelta(hours=1)

        booking = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
            google_event_id=None,
        )
        db_session.add(booking)
        await db_session.commit()
        await db_session.refresh(booking)

        # Fail on attempt 1 with 503, succeed on attempt 2
        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.side_effect = [
            GoogleCalendarAPIError("503 Service Unavailable"),
            {"id": "gcal_recovered_event_789", "status": "confirmed"},
        ]

        success = await sync_single_booking_with_retry(
            session=db_session,
            booking=booking,
            client=mock_client,
            max_retries=3,
            initial_delay=0.01,
        )

        assert success is True
        assert booking.google_event_id == "gcal_recovered_event_789"
        assert mock_client.create_event.await_count == 2

    async def test_retries_exhausted_marks_booking_sync_failed(
        self, db_session, sample_resource, sample_user
    ):
        """After exhausting all retries, the booking is marked with sync_failed status."""
        start = datetime.now(timezone.utc) + timedelta(days=3)
        end = start + timedelta(hours=1)

        booking = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
            google_event_id=None,
        )
        db_session.add(booking)
        await db_session.commit()
        await db_session.refresh(booking)

        # Persistent failure
        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.side_effect = GoogleCalendarAPIError("500 Internal Server Error")

        max_retries = 3
        success = await sync_single_booking_with_retry(
            session=db_session,
            booking=booking,
            client=mock_client,
            max_retries=max_retries,
            initial_delay=0.01,
        )

        assert success is False
        assert booking.status == "sync_failed"
        assert booking.google_event_id is None
        assert mock_client.create_event.await_count == max_retries

    async def test_sync_pending_batch_processing(
        self, db_session, sample_resource, sample_user
    ):
        """Verifies batch synchronization across multiple pending bookings."""
        now = datetime.now(timezone.utc)
        for i in range(3):
            b = Booking(
                resource_id=sample_resource.id,
                user_id=sample_user.id,
                start_time=now + timedelta(days=10, hours=i),
                end_time=now + timedelta(days=10, hours=i + 1),
                status="confirmed",
                google_event_id=None,
            )
            db_session.add(b)
        await db_session.commit()

        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.return_value = {"id": "gcal_batch_id", "status": "confirmed"}

        summary = await sync_pending_bookings(
            session=db_session,
            client=mock_client,
            max_retries=2,
        )

        assert summary["processed"] >= 3
        assert summary["synced"] >= 3
        assert summary["failed"] == 0
