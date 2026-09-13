"""
Google Calendar Sync Resilience Simulation.

Runs the synchronization workflow 200 times against a simulated Google Calendar API
with an artificially injected ~10% transient failure rate (e.g. 503 Service Unavailable / 429 Rate Limit).
Measures how exponential backoff retry logic recovers from network flakiness.
"""

import asyncio
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from backend.app.models import Booking
from backend.app.services.google_sync import (
    sync_single_booking_with_retry,
    GoogleCalendarClient,
    GoogleCalendarAPIError,
)


class FlakyGoogleCalendarClient(GoogleCalendarClient):
    """
    Simulates real-world external API instability with an injected failure rate.
    """
    def __init__(self, failure_rate: float = 0.10):
        self.failure_rate = failure_rate
        self.total_api_calls = 0
        self.transient_failures_injected = 0

    async def create_event(self, summary: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        self.total_api_calls += 1
        # Injected transient failure
        if random.random() < self.failure_rate:
            self.transient_failures_injected += 1
            raise GoogleCalendarAPIError("503 Service Unavailable / Network Flake")

        return {
            "id": f"gcal_sim_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{random.randint(1000, 9999)}",
            "status": "confirmed",
        }


class MockAsyncSession:
    """Lightweight in-memory session stub for high-speed simulation."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


async def run_resilience_simulation(num_runs: int = 200, failure_rate: float = 0.10, max_retries: int = 3):
    print("=" * 70)
    print(f" GOOGLE CALENDAR SYNC RESILIENCE SIMULATION ({num_runs} RUNS)")
    print("=" * 70)
    print(f"Injected Transient API Failure Rate: {failure_rate * 100:.1f}%")
    print(f"Max Exponential Backoff Retries:     {max_retries} attempts\n")

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

    print(" SIMULATION METRICS")
    print("-" * 70)
    print(f"Total Sync Operations Dispatched:       {num_runs}")
    print(f"Total Underlying Raw API Invocations:   {client.total_api_calls}")
    print(f"Raw Injected API Failures (503s/429s):  {client.transient_failures_injected}")
    print(f"Succeeded on 1st Attempt:               {recovered_first_try}")
    print(f"Recovered via Exponential Retry:        {recovered_with_retry}")
    print(f"Permanent Failures (Marked sync_failed): {permanent_failures}")
    print("-" * 70)
    print(f"Raw API Reliability:                    {baseline_success_rate:.1f}%")
    print(f"Effective Throughput with Retry Engine: {effective_success_rate:.2f}%")
    print("=" * 70)

    # Theoretical reliability: 1 - (failure_rate)^max_retries
    theoretical_max = (1.0 - (failure_rate ** max_retries)) * 100.0
    print(f"Theoretical Max Availability (3 tries): {theoretical_max:.2f}%")
    print(f"Actual Measured Availability:           {effective_success_rate:.2f}%\n")


if __name__ == "__main__":
    asyncio.run(run_resilience_simulation(num_runs=200, failure_rate=0.10, max_retries=3))
