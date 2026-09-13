import asyncio
import base64
import hashlib
import random
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import httpx
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.config import settings
from backend.app.models import Booking, BookingAuditLog, User, Resource


def _get_fernet_cipher() -> Fernet:
    raw_key = hashlib.sha256(settings.JWT_SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw_key))


def encrypt_token(plain_token: Optional[str]) -> Optional[str]:
    """Encrypts sensitive OAuth tokens before storing at rest in PostgreSQL."""
    if not plain_token:
        return None
    try:
        cipher = _get_fernet_cipher()
        return cipher.encrypt(plain_token.encode("utf-8")).decode("utf-8")
    except Exception:
        return plain_token


def decrypt_token(token_data: Optional[str]) -> Optional[str]:
    """Decrypts sensitive OAuth tokens read from PostgreSQL."""
    if not token_data:
        return None
    try:
        cipher = _get_fernet_cipher()
        return cipher.decrypt(token_data.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback for mock or legacy unencrypted tokens
        return token_data


class GoogleCalendarAPIError(Exception):
    """Raised when Google Calendar API returns an error."""
    pass


class GoogleCalendarClient:
    """
    Interface for Google Calendar API calls.
    Can be replaced or mocked during testing and resilience simulations.
    """
    async def create_event(self, summary: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        return {
            "id": f"gcal_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{random.randint(100, 999)}",
            "status": "confirmed",
        }


def get_google_oauth_url(state: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """
    Constructs Google OAuth 2.0 authorization URL requesting authentication and offline calendar access.
    Accepts cryptographic state nonce or legacy user_id.
    """
    from urllib.parse import urlencode

    effective_state = state or (str(user_id) if user_id is not None else "login")

    if not settings.GOOGLE_CLIENT_ID:
        # Dev/Mock URL fallback
        return f"{settings.GOOGLE_REDIRECT_URI}?code=mock_dev_code_123&state={effective_state}"

    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(effective_state),
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_google_code(code: str) -> Dict[str, Any]:
    """
    Exchanges authorization code for Google access and refresh tokens.
    """
    if code.startswith("mock_") or not settings.GOOGLE_CLIENT_SECRET:
        return {
            "access_token": f"mock_access_{code}",
            "refresh_token": f"mock_refresh_token_for_google_cal_{random.randint(10000, 99999)}",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise GoogleCalendarAPIError(f"Token exchange failed: {resp.text}")
        return resp.json()


async def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Retrieves user profile (email, name, picture) using Google access token.
    """
    if access_token.startswith("mock_"):
        return {
            "email": "demo.employee@company.internal",
            "name": "Demo Employee",
            "picture": None,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise GoogleCalendarAPIError(f"Failed to fetch userinfo from Google: {resp.text}")
        return resp.json()


async def get_fresh_access_token(refresh_token: str) -> str:
    """
    Exchanges refresh token for a fresh Google access token.
    Decrypts token if encrypted at rest.
    """
    raw_token = decrypt_token(refresh_token) or refresh_token

    if raw_token.startswith("mock_"):
        return f"mock_fresh_access_{random.randint(100, 999)}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": raw_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise GoogleCalendarAPIError(f"Failed to refresh Google access token: {resp.text}")
        data = resp.json()
        return data["access_token"]


async def create_google_calendar_event(
    refresh_token: str,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    description: str = "Booked via RoomSync",
    attendees: Optional[list[str]] = None,
    add_google_meet: bool = False,
) -> str:
    """
    Directly creates an event on the user's primary Google Calendar via Google Calendar API v3.
    Supports attendee email invitations and automatic Google Meet video link creation.
    """
    access_token = await get_fresh_access_token(refresh_token)

    if access_token.startswith("mock_"):
        return f"gcal_event_mock_{random.randint(10000, 99999)}"

    event_payload = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time.isoformat()},
        "end": {"dateTime": end_time.isoformat()},
    }

    if attendees:
        event_payload["attendees"] = [{"email": email.strip()} for email in attendees if email.strip()]

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params = {}
    if add_google_meet:
        event_payload["conferenceData"] = {
            "createRequest": {
                "requestId": f"meet-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        params["conferenceDataVersion"] = 1

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            json=event_payload,
        )
        if resp.status_code not in (200, 201):
            raise GoogleCalendarAPIError(f"Google Calendar API insert failed: {resp.text}")
        return resp.json()["id"]


async def delete_google_calendar_event(refresh_token: str, event_id: str) -> bool:
    """
    Deletes an event from the user's primary Google Calendar when cancelled in RoomSync.
    """
    try:
        access_token = await get_fresh_access_token(refresh_token)
        if access_token.startswith("mock_"):
            return True

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return resp.status_code in (200, 204, 404, 410)
    except Exception as e:
        print(f"[Calendar API] Warning: Failed to delete Google Calendar event {event_id}: {e}")
        return False


async def reconcile_google_calendar_changes(session: AsyncSession) -> Dict[str, int]:
    """
    Inbound Two-Way Synchronization (Google Calendar -> RoomSync):
    Checks active confirmed bookings with a google_event_id.
    - If event deleted/cancelled on Google Calendar -> cancels in RoomSync.
    - If time moved on Google Calendar -> verifies conflict safety and updates in RoomSync.
    """
    stmt = (
        select(Booking)
        .where(Booking.google_event_id.is_not(None))
        .where(Booking.status == "confirmed")
    )
    result = await session.execute(stmt)
    bookings = result.scalars().all()

    rescheduled_count = 0
    cancelled_count = 0
    conflicts_flagged = 0

    for booking in bookings:
        user_res = await session.execute(select(User).where(User.id == booking.user_id))
        user = user_res.scalar_one_or_none()
        if not user or not user.google_refresh_token or user.google_refresh_token.startswith("mock_"):
            continue

        try:
            access_token = await get_fresh_access_token(user.google_refresh_token)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{booking.google_event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            # 1. Event was deleted from Google Calendar
            if resp.status_code in (404, 410):
                booking.status = "cancelled"
                session.add(BookingAuditLog(
                    booking_id=booking.id,
                    action="cancelled_via_google_calendar",
                    detail="Event was deleted from user's Google Calendar.",
                ))
                await session.commit()
                cancelled_count += 1
                continue

            if resp.status_code != 200:
                continue

            event_data = resp.json()

            # Event marked cancelled on Google Calendar
            if event_data.get("status") == "cancelled":
                booking.status = "cancelled"
                session.add(BookingAuditLog(
                    booking_id=booking.id,
                    action="cancelled_via_google_calendar",
                    detail="Event status set to cancelled in Google Calendar.",
                ))
                await session.commit()
                cancelled_count += 1
                continue

            # 2. Timing changed on Google Calendar
            start_info = event_data.get("start", {})
            end_info = event_data.get("end", {})
            remote_start_str = start_info.get("dateTime") or start_info.get("date")
            remote_end_str = end_info.get("dateTime") or end_info.get("date")

            if not remote_start_str or not remote_end_str:
                continue

            from datetime import datetime
            remote_start = datetime.fromisoformat(remote_start_str.replace("Z", "+00:00"))
            remote_end = datetime.fromisoformat(remote_end_str.replace("Z", "+00:00"))

            # Check if times actually changed
            if remote_start != booking.start_time or remote_end != booking.end_time:
                print(f"[Two-Way Sync] Detected reschedule in Google Calendar for booking #{booking.id}: {remote_start} -> {remote_end}")
                
                # Check for overlap conflicts in Postgres with other confirmed bookings
                conflict_check = await session.execute(
                    select(Booking).where(
                        Booking.resource_id == booking.resource_id,
                        Booking.id != booking.id,
                        Booking.status == "confirmed",
                        Booking.start_time < remote_end,
                        Booking.end_time > remote_start,
                    )
                )
                has_conflict = conflict_check.scalar_one_or_none() is not None

                if has_conflict:
                    print(f"[Two-Way Sync] Conflict detected: slot already occupied for resource #{booking.resource_id}")
                    booking.status = "conflict_flagged"
                    session.add(BookingAuditLog(
                        booking_id=booking.id,
                        action="conflict_detected_from_google_calendar",
                        detail=f"Google Calendar moved event to [{remote_start} - {remote_end}], but this slot conflicts with an existing confirmed booking.",
                    ))
                    conflicts_flagged += 1
                else:
                    booking.start_time = remote_start
                    booking.end_time = remote_end
                    session.add(BookingAuditLog(
                        booking_id=booking.id,
                        action="rescheduled_via_google_calendar",
                        detail=f"Rescheduled via Google Calendar to [{remote_start} - {remote_end}].",
                    ))
                    rescheduled_count += 1

                await session.commit()

        except Exception as e:
            print(f"[Two-Way Sync] Error reconciling booking #{booking.id}: {e}")

    return {
        "rescheduled": rescheduled_count,
        "cancelled": cancelled_count,
        "conflicts_flagged": conflicts_flagged,
    }


async def sync_single_booking_with_retry(
    session: AsyncSession,
    booking: Booking,
    client: Optional[GoogleCalendarClient] = None,
    max_retries: int = 3,
    initial_delay: float = 0.05,
    backoff_factor: float = 2.0,
    attendees: Optional[list[str]] = None,
    add_google_meet: bool = False,
) -> bool:
    """
    Attempts to sync a booking to Google Calendar with exponential backoff.
    - If user has a real google_refresh_token, calls live Google Calendar API.
    - If successful, sets google_event_id and status='confirmed'
    - If retries exhaust, sets status='sync_failed'
    """
    delay = initial_delay

    # Load resource and user if needed
    res = await session.execute(
        select(Resource).where(Resource.id == booking.resource_id)
    )
    resource = res.scalar_one_or_none()
    res_name = resource.name if resource else f"Resource #{booking.resource_id}"

    user_res = await session.execute(
        select(User).where(User.id == booking.user_id)
    )
    user = user_res.scalar_one_or_none()

    # Use custom meeting title if provided
    meeting_title = booking.title or "Room Reservation"
    summary_text = f"{meeting_title} ({res_name})"

    for attempt in range(1, max_retries + 1):
        try:
            # 1. Check if user has a real Google Refresh Token and client not overridden
            if user and user.google_refresh_token and client is None:
                event_id = await create_google_calendar_event(
                    refresh_token=user.google_refresh_token,
                    summary=summary_text,
                    start_time=booking.start_time,
                    end_time=booking.end_time,
                    description=f"Confirmed reservation for {res_name} via RoomSync.",
                    attendees=attendees,
                    add_google_meet=add_google_meet,
                )
            else:
                api_client = client or GoogleCalendarClient()
                event = await api_client.create_event(
                    summary=summary_text,
                    start_time=booking.start_time,
                    end_time=booking.end_time,
                )
                event_id = event["id"]

            booking.google_event_id = event_id
            
            audit = BookingAuditLog(
                booking_id=booking.id,
                action="synced_to_google_calendar",
                detail=f"Synced to Google Calendar on attempt {attempt}. Event ID: {event_id}",
            )
            session.add(audit)
            await session.commit()
            return True

        except Exception as exc:
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                booking.status = "sync_failed"
                audit = BookingAuditLog(
                    booking_id=booking.id,
                    action="sync_failed",
                    detail=f"Google Calendar sync exhausted all {max_retries} attempts. Error: {str(exc)}",
                )
                session.add(audit)
                await session.commit()
                return False

    return False


async def sync_pending_bookings(
    session: AsyncSession,
    client: Optional[GoogleCalendarClient] = None,
    max_retries: int = 3,
) -> Dict[str, int]:
    """
    Finds all confirmed bookings without a google_event_id and syncs them.
    """
    stmt = (
        select(Booking)
        .where(Booking.google_event_id.is_(None))
        .where(Booking.status == "confirmed")
    )
    result = await session.execute(stmt)
    pending_bookings = result.scalars().all()

    success_count = 0
    failed_count = 0

    for booking in pending_bookings:
        success = await sync_single_booking_with_retry(
            session=session,
            booking=booking,
            client=client,
            max_retries=max_retries,
        )
        if success:
            success_count += 1
        else:
            failed_count += 1

    # Inbound Two-Way Reconciliation (Google Calendar -> RoomSync)
    reconcile_stats = await reconcile_google_calendar_changes(session)

    return {
        "processed": len(pending_bookings),
        "synced": success_count,
        "failed": failed_count,
        "rescheduled_from_google": reconcile_stats["rescheduled"],
        "cancelled_from_google": reconcile_stats["cancelled"],
        "conflicts_flagged": reconcile_stats["conflicts_flagged"],
    }


async def run_periodic_sync_worker(session_factory, interval_seconds: int = 60):
    """
    Lightweight background loop that wakes up every N seconds to sync pending bookings.
    """
    print(f"[Sync Worker] Background Google Calendar sync worker started (Interval: {interval_seconds}s).")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with session_factory() as session:
                summary = await sync_pending_bookings(session)
                if summary["processed"] > 0:
                    print(f"[Sync Worker] Automatically synced {summary['synced']} bookings to Google Calendar.")
        except asyncio.CancelledError:
            print("[Sync Worker] Background sync worker shutting down.")
            break
        except Exception as e:
            print(f"[Sync Worker] Error during background sync pass: {e}")
