"""
Script 3: Concurrency Test — Constraint Enabled
Fires 100 concurrent booking requests at the same resource for the exact same time slot.
Verifies that PostgreSQL's GiST exclusion constraint guarantees strictly 1 success and 99 failures.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.app.config import settings
from backend.app.database import Base
from backend.app.models import User, Resource, Booking
from backend.app.schemas import BookingCreate
from backend.app.services.booking_service import (
    create_booking_constraint_protected,
    BookingConflictError,
)


async def setup_test_data(engine):
    """Prepares clean resource and employee in PostgreSQL."""
    async with engine.begin() as conn:
        if "postgresql" in settings.DATABASE_URL:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = User(name="Concurrency Tester", email=f"concurrency_user_{int(datetime.now(timezone.utc).timestamp())}@company.internal")
        resource = Resource(
            name="Boardroom (Constraint Concurrency Test)",
            type="room",
            capacity=15,
            min_notice_minutes=0,
            cancellation_window_minutes=0,
        )
        session.add_all([user, resource])
        await session.commit()
        await session.refresh(user)
        await session.refresh(resource)
        return user.id, resource.id


async def main():
    print("=" * 70)
    print(" ROOMSYNC CONCURRENCY TEST (POSTGRES GIST CONSTRAINT ENABLED)")
    print("=" * 70)
    print(f"Connecting to: {settings.DATABASE_URL}\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=25, max_overflow=20, pool_timeout=60)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    user_id, resource_id = await setup_test_data(engine)

    num_requests = 100
    target_start = datetime.now(timezone.utc) + timedelta(days=2, hours=14)
    target_end = target_start + timedelta(hours=1)

    print(f"[*] Dispatching {num_requests} simultaneous booking requests for identical slot:")
    print(f"    Resource ID: {resource_id} | Slot: [{target_start} -> {target_end}]")

    async def single_request(idx: int):
        async with session_factory() as session:
            booking_data = BookingCreate(
                resource_id=resource_id,
                user_id=user_id,
                start_time=target_start,
                end_time=target_end,
                title=f"Concurrent Attempt #{idx + 1}",
            )
            try:
                await create_booking_constraint_protected(session=session, data=booking_data)
                return "SUCCESS"
            except BookingConflictError:
                return "CONFLICT"
            except Exception as e:
                return f"ERROR: {type(e).__name__}: {e}"

    tasks = [single_request(i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)

    success_count = results.count("SUCCESS")
    conflict_count = results.count("CONFLICT")
    errors = [r for r in results if r not in ("SUCCESS", "CONFLICT")]
    error_count = len(errors)

    print("\n" + "-" * 70)
    print(" CONCURRENCY RESULTS")
    print("-" * 70)
    print(f"Total Concurrent Requests Fired: {num_requests}")
    print(f"Successful Reservations:         {success_count}")
    print(f"Rejected Conflict Errors (409):  {conflict_count}")
    if error_count > 0:
        print(f"Unexpected Errors ({error_count}):")
        for err in errors[:5]:
            print(f"   -> {err}")
    print("-" * 70)

    # Standardized metric line for documentation
    print(f"\n[METRIC] Concurrency (constraint): {success_count}/{num_requests} succeeded, {conflict_count}/{num_requests} failed")

    if success_count == 1 and conflict_count == (num_requests - 1):
        print("[VERIFIED] Exactly 1 request succeeded; zero race-condition double bookings occurred.\n")
    else:
        print(f"[WARNING] Expected 1 success and 99 conflicts. Got: {success_count} / {conflict_count}\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
