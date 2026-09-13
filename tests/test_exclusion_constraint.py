import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import IntegrityError
from backend.app.models import Booking, Resource, User


@pytest.mark.asyncio
class TestPostgresExclusionConstraint:
    """
    Direct tests for PostgreSQL's EXCLUDE USING gist constraint on the bookings table.
    Runs against the real PostgreSQL database engine to test range exclusion.
    """

    async def test_exact_duplicate_time_range_raises_integrity_error(
        self, db_session, sample_resource, sample_user
    ):
        """1. Exact-duplicate time range for the same resource -> assert IntegrityError."""
        start = datetime.now(timezone.utc) + timedelta(days=1)
        end = start + timedelta(hours=1)

        b1 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
        )
        db_session.add(b1)
        await db_session.commit()

        # Duplicate attempt for identical resource and time
        b2 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
        )
        db_session.add(b2)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_partially_overlapping_range_raises_integrity_error(
        self, db_session, sample_resource, sample_user
    ):
        """2. Partially overlapping range -> assert IntegrityError."""
        base_time = datetime.now(timezone.utc) + timedelta(days=2)
        start1 = base_time
        end1 = base_time + timedelta(hours=2)

        b1 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start1,
            end_time=end1,
            status="confirmed",
        )
        db_session.add(b1)
        await db_session.commit()

        # Overlapping attempt: starts 1 hour into slot 1
        start2 = base_time + timedelta(hours=1)
        end2 = base_time + timedelta(hours=3)

        b2 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start2,
            end_time=end2,
            status="confirmed",
        )
        db_session.add(b2)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_adjacent_back_to_back_range_succeeds(
        self, db_session, sample_resource, sample_user
    ):
        """
        3. Adjacent, non-overlapping range (e.g. back-to-back: [10:00-11:00) and [11:00-12:00))
        -> assert success because PostgreSQL ranges are half-open [) by default.
        """
        base_time = datetime.now(timezone.utc) + timedelta(days=3)
        slot1_start = base_time
        slot1_end = base_time + timedelta(hours=1)

        slot2_start = slot1_end  # adjacent boundary
        slot2_end = slot2_start + timedelta(hours=1)

        b1 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=slot1_start,
            end_time=slot1_end,
            status="confirmed",
        )
        b2 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=slot2_start,
            end_time=slot2_end,
            status="confirmed",
        )

        db_session.add(b1)
        await db_session.commit()

        db_session.add(b2)
        await db_session.commit()

        assert b1.id is not None
        assert b2.id is not None
        assert b1.id != b2.id

    async def test_identical_time_range_different_resource_succeeds(
        self, db_session, sample_resource, sample_user
    ):
        """4. Identical time range for a DIFFERENT resource -> assert success."""
        base_time = datetime.now(timezone.utc) + timedelta(days=4)
        start = base_time
        end = base_time + timedelta(hours=1)

        # Create second resource
        resource2 = Resource(
            name="Studio Podcast Mic Kit",
            type="equipment",
            min_notice_minutes=15,
            cancellation_window_minutes=10,
        )
        db_session.add(resource2)
        await db_session.commit()
        await db_session.refresh(resource2)

        b1 = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
        )
        b2 = Booking(
            resource_id=resource2.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
        )

        db_session.add(b1)
        await db_session.commit()

        db_session.add(b2)
        await db_session.commit()

        assert b1.id != b2.id
        assert b1.resource_id != b2.resource_id
