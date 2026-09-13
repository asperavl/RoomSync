"""
Script 6: Google Calendar Sync Reliability & Resilience Test
Dispatches 200 booking synchronizations against a mock client with an injected 10%
transient failure rate (HTTP 503 Service Unavailable / 429 Rate Limit).
Verifies that 3-attempt exponential backoff recovers transient drops.

Standardized Metric Output:
[METRIC] Effective sync success rate: X.X% (Y/200 succeeded)
"""

import asyncio
import sys
import os
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.models import Booking
from backend.app.services.google_sync import (
    sync_single_booking_with_retry,
    GoogleCalendarClient,
    GoogleCalendarAPIError,
)


class FlakyGoogleCalendarClient(GoogleCalendarClient):
    """Simulates external Google Calendar API with controlled transient failure injection."""
    def __init__(self, failure_rate: float = 0.10):
        self.failure_rate = failure_rate
        self.total_api_calls = 0
        self.transient_failures_injected = 0

    async def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        attendee_emails: list = None,
        create_meet_link: bool = False,
    ) -> Dict[str, Any]:
        self.total_api_calls += 1
        if random.random() < self.failure_rate:
            self.transient_failures_injected += 1
            raise GoogleCalendarAPIError("503 Service Unavailable (Injected Network Transient)")

        return {
            "id": f"gcal_sim_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{random.randint(1000, 9999)}",
            "status": "confirmed",
            "hangoutLink": "https://meet.google.com/sim-test-call" if create_meet_link else None,
        }


class MockScalarResult:
    def __init__(self, val):
        self.val = val

    def scalar_one_or_none(self):
        return self.val


class MockAsyncSession:
    """In-memory session stub for fast async execution."""
    def __init__(self):
        self.added = []
        self.dummy_resource = type("Resource", (), {"name": "Boardroom Alpha"})()
        self.dummy_user = type("User", (), {"name": "Test Engineer", "google_refresh_token": None})()

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, statement):
        stmt_str = str(statement).lower()
        if "resources" in stmt_str:
            return MockScalarResult(self.dummy_resource)
        return MockScalarResult(self.dummy_user)

    async def commit(self):
        pass


async def main():
    num_runs = 200
    failure_rate = 0.10
    max_retries = 3

    print("=" * 70)
    print(f" GOOGLE CALENDAR SYNC RELIABILITY BENCHMARK ({num_runs} RUNS)")
    print("=" * 70)
    print(f"Injected Transient Failure Rate: {failure_rate * 100:.1f}%")
    print(f"Max Exponential Backoff Retries: {max_retries} attempts\n")

    client = FlakyGoogleCalendarClient(failure_rate=failure_rate)
    now = datetime.now(timezone.utc)

    recovered_first_try = 0
    recovered_with_retry = 0
    permanent_failures = 0

    for i in range(1, num_runs + 1):
        booking = Booking(
            id=i,
            resource_id=1,
            user_id=1,
            start_time=now + timedelta(hours=i),
            end_time=now + timedelta(hours=i + 1),
            status="confirmed",
            title=f"Sync Test Meeting #{i}",
        )
        session = MockAsyncSession()

        calls_before = client.total_api_calls
        success = await sync_single_booking_with_retry(
            session=session,
            booking=booking,
            client=client,
            max_retries=max_retries,
            initial_delay=0.001,  # Fast simulation delay
            backoff_factor=1.5,
        )
        calls_during = client.total_api_calls - calls_before

        if success:
            if calls_during == 1:
                recovered_first_try += 1
            else:
                recovered_with_retry += 1
        else:
            permanent_failures += 1

    total_successful = recovered_first_try + recovered_with_retry
    effective_success_rate = (total_successful / num_runs) * 100.0
    baseline_success_rate = (1.0 - failure_rate) * 100.0

    print("-" * 70)
    print(f"Total Operations Dispatched:     {num_runs}")
    print(f"Total Underlying Raw API Calls:  {client.total_api_calls}")
    print(f"Injected Transient Drop Events:  {client.transient_failures_injected}")
    print(f"Succeeded on 1st Attempt:        {recovered_first_try}")
    print(f"Recovered via Retry Backoff:     {recovered_with_retry}")
    print(f"Exhausted Failures:              {permanent_failures}")
    print("-" * 70)
    print(f"Baseline Single-Attempt Rate:    {baseline_success_rate:.1f}%")
    print(f"Effective Throughput with Retry: {effective_success_rate:.1f}%")
    print("=" * 70)

    # Standardized metric output
    print(f"\n[METRIC] Effective sync success rate: {effective_success_rate:.1f}% ({total_successful}/{num_runs} succeeded)\n")


if __name__ == "__main__":
    asyncio.run(main())
