"""
Script 5: Load & Index Query Benchmark (with Faker)
Seeds 2,000+ synthetic bookings across 50+ resources over a 6-month timeline.
Executes EXPLAIN (ANALYZE, BUFFERS) before and after creating the composite index:
idx_bookings_resource_time ON bookings (resource_id, start_time, end_time).

Standardized Metrics Output:
[METRIC] Query time before indexing: X.XX ms
[METRIC] Query time after indexing: Y.YY ms
"""

import asyncio
import sys
import os
import random
import re
from datetime import datetime, timezone, timedelta
from faker import Faker

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.app.config import settings
from backend.app.database import Base
from backend.app.models import User, Resource, Booking

fake = Faker()


async def seed_data(session: AsyncSession, num_resources: int = 50, num_bookings: int = 2200):
    print(f"[*] Seeding {num_resources} resources and {num_bookings}+ bookings across 6 months...")

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

    # Generate 2,250 synthetic non-overlapping bookings across resources
    now = datetime.now(timezone.utc)
    base_start = now - timedelta(days=90)

    bookings = []
    for res in resources:
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
                title=f"Synthetic Meeting: {fake.catch_phrase()[:30]}",
                google_event_id=f"gcal_{fake.uuid4()[:12]}",
            )
            bookings.append(b)
            # Advance time interval
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


async def run_explain_analyze(session: AsyncSession, resource_id: int, force_seq_scan: bool = False):
    if force_seq_scan:
        await session.execute(text("SET enable_seqscan = on;"))
        await session.execute(text("SET enable_indexscan = off;"))
        await session.execute(text("SET enable_bitmapscan = off;"))
    else:
        await session.execute(text("SET enable_seqscan = on;"))
        await session.execute(text("SET enable_indexscan = on;"))
        await session.execute(text("SET enable_bitmapscan = on;"))

    query_start = datetime.now(timezone.utc) - timedelta(days=30)
    query_end = datetime.now(timezone.utc) + timedelta(days=30)

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
    print(" ROOMSYNC LOAD & EXPLAIN ANALYZE BENCHMARK")
    print("=" * 70)
    print(f"Connecting to: {settings.DATABASE_URL}\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Initialize schema
    async with engine.begin() as conn:
        if "postgresql" in settings.DATABASE_URL:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed database
    async with async_session() as session:
        target_resource_id = await seed_data(session, num_resources=50, num_bookings=2250)

    # 3. Test WITHOUT Index (Baseline Sequential Scan)
    print("\n[*] Measuring baseline Sequential Scan across 2,250+ booking rows...")
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS idx_bookings_resource_time;"))

    async with async_session() as session:
        unindexed_plan, unindexed_time = await run_explain_analyze(session, target_resource_id, force_seq_scan=True)

    print(f"    -> Unindexed (Seq Scan) Time: {unindexed_time:.2f} ms")
    for line in unindexed_plan[:4]:
        print(f"       {line}")

    # 4. Test WITH Composite Index
    print("\n[*] Creating composite index: idx_bookings_resource_time (resource_id, start_time, end_time)...")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE INDEX idx_bookings_resource_time ON bookings (resource_id, start_time, end_time);"
        ))

    async with async_session() as session:
        indexed_plan, indexed_time = await run_explain_analyze(session, target_resource_id, force_seq_scan=False)

    print(f"    -> Indexed (Index Scan) Time: {indexed_time:.2f} ms")
    for line in indexed_plan[:4]:
        print(f"       {line}")

    speedup = (unindexed_time / indexed_time) if indexed_time > 0 else 1.0

    print("\n" + "=" * 70)
    print(" BENCHMARK SUMMARY & STANDARDIZED METRICS")
    print("=" * 70)
    print(f"Before Index (Seq Scan):  {unindexed_time:.2f} ms")
    print(f"After Index (Index Scan): {indexed_time:.2f} ms")
    print(f"Speedup Multiplier:       {speedup:.1f}x faster")
    print("-" * 70)

    # Standardized metric outputs
    print(f"\n[METRIC] Query time before indexing: {unindexed_time:.2f} ms")
    print(f"[METRIC] Query time after indexing: {indexed_time:.2f} ms\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
