"""
Database initialization and seeding script for RoomSync.

1. Connects to PostgreSQL.
2. Ensures the 'btree_gist' extension is enabled.
3. Creates all tables (users, resources, bookings, booking_audit_log).
4. Seeds initial conference rooms, equipment, and a test employee user.
"""

import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text, select
from backend.app.config import settings
from backend.app.database import Base
from backend.app.models import User, Resource


INITIAL_RESOURCES = [
    {
        "name": "Executive Boardroom Alpha",
        "type": "room",
        "capacity": 16,
        "min_notice_minutes": 30,
        "cancellation_window_minutes": 15,
    },
    {
        "name": "Design Huddle Room Beta",
        "type": "room",
        "capacity": 6,
        "min_notice_minutes": 15,
        "cancellation_window_minutes": 10,
    },
    {
        "name": "All-Hands Agora Hall",
        "type": "room",
        "capacity": 50,
        "min_notice_minutes": 60,
        "cancellation_window_minutes": 30,
    },
    {
        "name": "4K Laser Projector Mobile Unit",
        "type": "equipment",
        "capacity": None,
        "min_notice_minutes": 15,
        "cancellation_window_minutes": 15,
    },
    {
        "name": "Studio Podcast Mic & Audio Kit",
        "type": "equipment",
        "capacity": None,
        "min_notice_minutes": 30,
        "cancellation_window_minutes": 15,
    },
]

INITIAL_USERS = [
    {
        "name": "Demo Employee",
        "email": "employee@company.internal",
    },
    {
        "name": "Office Lead",
        "email": "office.lead@company.internal",
    },
]


async def init_and_seed():
    print("=" * 60)
    print(" ROOMSYNC DATABASE INITIALIZER & SEEDER")
    print("=" * 60)
    print(f"Connecting to: {settings.DATABASE_URL}\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with engine.begin() as conn:
            print("[1/3] Enabling PostgreSQL 'btree_gist' extension...")
            if "postgresql" in settings.DATABASE_URL:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
                print("      -> btree_gist enabled.")

            print("[2/3] Creating tables (users, resources, bookings, audit log)...")
            await conn.run_sync(Base.metadata.create_all)
            print("      -> Tables verified/created successfully.")

        async with session_factory() as session:
            print("[3/3] Seeding initial resources and users...")
            
            # Check existing resources
            existing_res = await session.execute(select(Resource))
            if not existing_res.scalars().first():
                for res_data in INITIAL_RESOURCES:
                    session.add(Resource(**res_data))
                print(f"      -> Seeded {len(INITIAL_RESOURCES)} shared resources.")
            else:
                print("      -> Resources already exist. Skipping resource seed.")

            # Check existing users
            existing_users = await session.execute(select(User))
            if not existing_users.scalars().first():
                for user_data in INITIAL_USERS:
                    session.add(User(**user_data))
                print(f"      -> Seeded {len(INITIAL_USERS)} initial users.")
            else:
                print("      -> Users already exist. Skipping user seed.")

            await session.commit()

        print("\n" + "=" * 60)
        print(" DATABASE SETUP COMPLETE! RoomSync is ready to run.")
        print("=" * 60)

    except Exception as e:
        print("\n[ERROR] Database initialization failed!")
        print(f"Details: {e}\n")
        print("Troubleshooting:")
        print("1. Ensure PostgreSQL is running on localhost:5432.")
        print("2. Ensure database 'roomsync' exists (e.g. `createdb roomsync`).")
        print("3. Check credentials in your .env file.")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_and_seed())
