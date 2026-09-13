import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from backend.app.models import Booking
from backend.app.services.google_sync import (
    sync_single_booking_with_retry,
    sync_pending_bookings,
    GoogleCalendarClient,
    GoogleCalendarAPIError,
)


@pytest.mark.asyncio
class TestGoogleCalendarSync:
    """
    Tests for Google Calendar synchronization with exponential backoff and retry failure states.
    Uses unittest.mock to simulate external API responses and transient failures.
    """

    async def test_successful_sync_stores_google_event_id(
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

        # Mock client returning an event ID
        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.return_value = {
            "id": "gcal_event_xyz123",
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
        assert booking.google_event_id == "gcal_event_xyz123"
        assert booking.status == "confirmed"
        mock_client.create_event.assert_awaited_once()

    async def test_simulated_api_failure_triggers_retry_logic(
        self, db_session, sample_resource, sample_user
    ):
        """A transient API failure triggers retries and eventually succeeds."""
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

        # Mock client that fails on attempt 1, succeeds on attempt 2
        mock_client = AsyncMock(spec=GoogleCalendarClient)
        mock_client.create_event.side_effect = [
            GoogleCalendarAPIError("503 Service Unavailable"),
            {"id": "gcal_event_recovered", "status": "confirmed"},
        ]

        success = await sync_single_booking_with_retry(
            session=db_session,
            booking=booking,
            client=mock_client,
            max_retries=3,
            initial_delay=0.01,
        )

        assert success is True
        assert booking.google_event_id == "gcal_event_recovered"
        assert mock_client.create_event.await_count == 2

    async def test_exhausted_retries_marks_booking_sync_failed(
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

        # Mock client that persistently fails
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

    async def test_sync_pending_bookings_batch(
        self, db_session, sample_resource, sample_user
    ):
        """Verifies batch synchronization of multiple pending bookings."""
        now = datetime.now(timezone.utc)
        bookings = []
        for i in range(3):
            b = Booking(
                resource_id=sample_resource.id,
                user_id=sample_user.id,
                start_time=now + timedelta(days=5, hours=i),
                end_time=now + timedelta(days=5, hours=i + 1),
                status="confirmed",
                google_event_id=None,
            )
            db_session.add(b)
            bookings.append(b)
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

    def test_google_oauth_url_generation(self):
        """Verifies OAuth 2.0 authorization URL construction."""
        from backend.app.services.google_sync import get_google_oauth_url
        url = get_google_oauth_url(user_id=42)
        assert "state=42" in url
        assert "callback" in url

    async def test_google_oauth_code_exchange_dev_mode(self):
        """Verifies token exchange in dev/mock sandbox mode."""
        from backend.app.services.google_sync import exchange_google_code
        tokens = await exchange_google_code("mock_test_auth_code_999")
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "Bearer"
