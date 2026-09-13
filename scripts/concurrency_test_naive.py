"""
Script 4: Concurrency Benchmark — Naive Check-Then-Insert (Race Condition Demonstration)
Fires 100 concurrent booking requests at the same resource for the exact same time slot
using application-level SELECT-then-INSERT logic WITHOUT database-level exclusion constraints.

Demonstrates Time-of-Check to Time-of-Use (TOCTOU) race conditions: multiple workers read
the table before any commit, resulting in corrupted double-bookings.
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
from backend.app.models import User, Resource


async def setup_test_data(engine):
    """Prepares clean resource, employee, and unconstrained naive table in PostgreSQL."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bookings_naive_demo (
                id SERIAL PRIMARY KEY,
                resource_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                start_time TIMESTAMPTZ NOT NULL,
                end_time TIMESTAMPTZ NOT NULL,
                status VARCHAR DEFAULT 'confirmed',
                title VARCHAR
            )
        """))
        await conn.execute(text("TRUNCATE TABLE bookings_naive_demo"))

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = User(
            name="Naive Concurrency Tester",
            email=f"naive_tester_{int(datetime.now(timezone.utc).timestamp())}@company.internal"
        )
        resource = Resource(
            name="Boardroom (Naive Race Condition Test)",
            type="room",
            capacity=10,
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
    print(" ROOMSYNC CONCURRENCY TEST (NAIVE APPLICATION CHECK-THEN-INSERT)")
    print("=" * 70)
    print(f"Connecting to: {settings.DATABASE_URL}\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=25, max_overflow=20, pool_timeout=60)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    user_id, resource_id = await setup_test_data(engine)

    num_requests = 100
    target_start = datetime.now(timezone.utc) + timedelta(days=3, hours=10)
    target_end = target_start + timedelta(hours=1)

    print(f"[*] Dispatching {num_requests} simultaneous booking requests to NAIVE endpoint:")
    print(f"    Resource ID: {resource_id} | Slot: [{target_start} -> {target_end}]")

    # Barrier ensures all 100 workers establish connections before firing queries simultaneously
    barrier = asyncio.Barrier(num_requests)

    async def single_request(idx: int):
        async with session_factory() as session:
            try:
                # Wait for all 100 workers to align at the starting gate
                await barrier.wait()

                # Step 1: Naive SELECT check (application-level query)
                check_sql = text("""
                    SELECT id FROM bookings_naive_demo
                    WHERE resource_id = :res_id
                      AND status = 'confirmed'
                      AND start_time < :end_time
                      AND end_time > :start_time
                """)
                result = await session.execute(
                    check_sql,
                    {"res_id": resource_id, "start_time": target_start, "end_time": target_end}
                )
                if result.scalar_one_or_none():
                    return "CONFLICT"

                # Simulate realistic async network & ORM processing delay between check and insert
                await asyncio.sleep(0.01)

                # Step 2: Unconstrained INSERT
                insert_sql = text("""
                    INSERT INTO bookings_naive_demo (resource_id, user_id, start_time, end_time, status, title)
                    VALUES (:res_id, :user_id, :start_time, :end_time, 'confirmed', :title)
                """)
                await session.execute(
                    insert_sql,
                    {
                        "res_id": resource_id,
                        "user_id": user_id,
                        "start_time": target_start,
                        "end_time": target_end,
                        "title": f"Naive Attempt #{idx + 1}",
                    }
                )
                await session.commit()
                return "SUCCESS"
            except Exception as e:
                return f"ERROR: {type(e).__name__}: {e}"

    tasks = [single_request(i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)

    success_count = results.count("SUCCESS")
    conflict_count = results.count("CONFLICT")
    double_bookings = max(0, success_count - 1)

    print("\n" + "-" * 70)
    print(" NAIVE CONCURRENCY RESULTS")
    print("-" * 70)
    print(f"Total Concurrent Requests Fired: {num_requests}")
    print(f"Successful Reservations:         {success_count}")
    print(f"Rejected Conflict Errors:        {conflict_count}")
    print(f"Corrupted Double-Bookings:       {double_bookings}")
    print("-" * 70)

    # Standardized metric line
    print(f"\n[METRIC] Concurrency (naive): {success_count}/{num_requests} succeeded ({double_bookings} double-bookings)")

    if double_bookings > 0:
        print(f"[RACE CONDITION CONFIRMED] {double_bookings} double-bookings slipped through application-level checks.\n")
    else:
        print("[NOTICE] Zero double bookings observed this round.\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
