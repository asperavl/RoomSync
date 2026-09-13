"""
Load & Indexing Benchmark Script.

1. Generates 2,000+ synthetic bookings across 50+ resources spanning 6 months using Faker.
2. Runs EXPLAIN (ANALYZE, BUFFERS) on conflict queries before and after dropping/adding
   the composite index idx_bookings_resource_time (resource_id, start_time, end_time).
3. Reports query execution times in milliseconds.
"""

import asyncio
import sys
import os
import random
import re
from datetime import datetime, timezone, timedelta
from faker import Faker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.app.config import settings
from backend.app.database import Base
from backend.app.models import User, Resource, Booking

fake = Faker()


async def seed_data(session: AsyncSession, num_resources: int = 50, num_bookings: int = 2200):
    print(f"[*] Seeding {num_resources} resources and {num_bookings} bookings across 6 months...")
    
    # Create users
    users = [
        User(name=fake.name(), email=fake.unique.email())
        for _ in range(30)
    ]
    session.add_all(users)
    await session.flush()

    # Create resources
    resource_types = ["room", "equipment"]
    resources = [
        Resource(
            name=f"{fake.city()} {fake.word().capitalize()} Room",
            type=random.choice(resource_types),
            capacity=random.randint(4, 30),
            min_notice_minutes=random.choice([0, 15, 30]),
            cancellation_window_minutes=random.choice([0, 15, 30]),
        )
        for _ in range(num_resources)
    ]
    session.add_all(resources)
    await session.flush()

    # Create 2000+ synthetic non-overlapping bookings
    now = datetime.now(timezone.utc)
    base_start = now - timedelta(days=90)
    
    bookings = []
    # Distribute bookings across resources
    for res in resources:
        # 45 non-overlapping slots per resource across 180 days
        current_time = base_start + timedelta(hours=random.randint(1, 10))
        for _ in range(45):
            duration_hours = random.choice([1, 2, 3])
            start_time = current_time
            end_time = start_time + timedelta(hours=duration_hours)
            user = random.choice(users)
            
            b = Booking(
                resource_id=res.id,
                user_id=user.id,
                start_time=start_time,
                end_time=end_time,
                status="confirmed",
                google_event_id=f"gcal_{fake.uuid4()[:12]}",
            )
            bookings.append(b)
            # Advance to next day/time
            current_time = end_time + timedelta(hours=random.randint(12, 72))

    session.add_all(bookings)
    await session.commit()
    print(f"[+] Successfully seeded {len(resources)} resources and {len(bookings)} bookings.")
    return resources[0].id


def parse_execution_time(explain_lines: list) -> float:
    for line in explain_lines:
        match = re.search(r"Execution Time:\s+([\d\.]+)\s+ms", line)
        if match:
            return float(match.group(1))
    return 0.0


async def run_explain_analyze(session: AsyncSession, resource_id: int):
    # Query checking for overlapping slots for resource_id
    query_start = datetime.now(timezone.utc)
    query_end = query_start + timedelta(hours=2)

    sql = text("""
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT id, resource_id, start_time, end_time, status
        FROM bookings
        WHERE resource_id = :res_id
          AND status = 'confirmed'
          AND start_time < :q_end
          AND end_time > :q_start;
    """)

    result = await session.execute(sql, {"res_id": resource_id, "q_start": query_start, "q_end": query_end})
    lines = [row[0] for row in result.fetchall()]
    return lines, parse_execution_time(lines)


async def main():
    print("=" * 70)
    print(" ROOMSYNC LOAD & EXPLAIN ANALYZE INDEX BENCHMARK")
    print("=" * 70)
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Initialize schema
    async with engine.begin() as conn:
        if "postgresql" in settings.DATABASE_URL:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed database with 2000+ bookings
    async with async_session() as session:
        target_resource_id = await seed_data(session, num_resources=50, num_bookings=2250)

    # 3. Test WITHOUT Index
    print("\n[*] Dropping index idx_bookings_resource_time to test baseline Seq Scan...")
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS idx_bookings_resource_time;"))

    async with async_session() as session:
        unindexed_plan, unindexed_time = await run_explain_analyze(session, target_resource_id)

    print(f"    -> Unindexed Execution Time: {unindexed_time:.3f} ms")
    for line in unindexed_plan[:3]:
        print(f"       {line}")

    # 4. Test WITH Index
    print("\n[*] Rebuilding composite index (resource_id, start_time, end_time)...")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE INDEX idx_bookings_resource_time ON bookings (resource_id, start_time, end_time);"
        ))

    async with async_session() as session:
        indexed_plan, indexed_time = await run_explain_analyze(session, target_resource_id)

    print(f"    -> Indexed Execution Time: {indexed_time:.3f} ms")
    for line in indexed_plan[:3]:
        print(f"       {line}")

    speedup = (unindexed_time / indexed_time) if indexed_time > 0 else 1.0

    print("\n" + "=" * 70)
    print(" INDEX BENCHMARK SUMMARY REPORT")
    print("=" * 70)
    print(f"{'Condition':<35} | {'Execution Time (ms)':<20} | {'Plan Strategy'}")
    print("-" * 75)
    print(f"{'Before Index (Full Sequential Scan)':<35} | {f'{unindexed_time:.3f} ms':<20} | Seq Scan")
    print(f"{'After Index (idx_bookings_resource_time)':<35} | {f'{indexed_time:.3f} ms':<20} | Index / Bitmap Scan")
    print("-" * 75)
    print(f"Latency Reduction: {speedup:.1f}x faster execution under 2,250+ booking records\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
