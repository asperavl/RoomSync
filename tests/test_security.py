import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from backend.app.models import User, Resource, Booking
from backend.app.auth import create_access_token
from backend.app.services.google_sync import encrypt_token, decrypt_token


@pytest.mark.asyncio
class TestSecurityControls:
    """Automated security verification test suite for RoomSync."""

    async def test_users_endpoint_does_not_leak_refresh_tokens(self, client: AsyncClient, db_session):
        """Verify that GET /api/users does not expose google_refresh_token in response payloads."""
        unique_email = f"alice_{uuid.uuid4().hex[:8]}@company.internal"
        secret_refresh = "super_sensitive_google_refresh_token_xyz"
        test_user = User(
            name="Alice Security",
            email=unique_email,
            google_refresh_token=encrypt_token(secret_refresh),
        )
        db_session.add(test_user)
        await db_session.commit()

        resp = await client.get("/api/users")
        assert resp.status_code == 200
        users = resp.json()

        alice_entry = next((u for u in users if u["email"] == unique_email), None)
        assert alice_entry is not None
        # Must not contain google_refresh_token
        assert "google_refresh_token" not in alice_entry
        assert alice_entry.get("google_connected") is True

    async def test_booking_creation_requires_authentication(self, client: AsyncClient, sample_resource):
        """Verify that POST /api/bookings rejects unauthenticated requests with 401 Unauthorized."""
        start = datetime.now(timezone.utc) + timedelta(days=5)
        end = start + timedelta(hours=1)

        resp = await client.post(
            "/api/bookings",
            json={
                "resource_id": sample_resource.id,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "title": "Unauthenticated Attempt",
            },
        )
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]

    async def test_booking_creation_binds_authenticated_user_identity(
        self, client: AsyncClient, sample_resource, sample_user
    ):
        """Verify that POST /api/bookings binds booking to current_user.id regardless of request body."""
        token = create_access_token({"sub": str(sample_user.id), "email": sample_user.email, "name": sample_user.name})
        start = datetime.now(timezone.utc) + timedelta(days=6)
        end = start + timedelta(hours=1)

        resp = await client.post(
            "/api/bookings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "resource_id": sample_resource.id,
                "user_id": 99999,  # Malicious attempt to spoof another user ID
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "title": "Secure Identity Test",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # Verified: user_id is forced to authenticated user.id, spoofed user_id is ignored
        assert data["user_id"] == sample_user.id

    async def test_booking_cancellation_authorization_and_idor_protection(
        self, client: AsyncClient, db_session, sample_resource, sample_user
    ):
        """Verify IDOR protection: only the reservation owner can cancel their booking."""
        start = datetime.now(timezone.utc) + timedelta(days=7)
        end = start + timedelta(hours=1)

        # Create booking owned by sample_user
        booking = Booking(
            resource_id=sample_resource.id,
            user_id=sample_user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.commit()
        await db_session.refresh(booking)

        # Create another user (attacker) with unique email
        attacker_email = f"eve_{uuid.uuid4().hex[:8]}@company.internal"
        attacker = User(name="Eve Attacker", email=attacker_email)
        db_session.add(attacker)
        await db_session.commit()
        await db_session.refresh(attacker)

        attacker_token = create_access_token({"sub": str(attacker.id), "email": attacker.email, "name": attacker.name})
        owner_token = create_access_token({"sub": str(sample_user.id), "email": sample_user.email, "name": sample_user.name})

        # 1. Unauthenticated cancellation attempt -> 401
        resp_anon = await client.post(f"/api/bookings/{booking.id}/cancel", json={})
        assert resp_anon.status_code == 401

        # 2. Attacker attempting to cancel victim's booking -> 403 Forbidden
        resp_attacker = await client.post(
            f"/api/bookings/{booking.id}/cancel",
            headers={"Authorization": f"Bearer {attacker_token}"},
            json={"user_id": sample_user.id},
        )
        assert resp_attacker.status_code == 403
        assert "Permission Denied" in resp_attacker.json()["detail"]

        # 3. Legitimate owner cancellation -> 200 OK
        resp_owner = await client.post(
            f"/api/bookings/{booking.id}/cancel",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        )
        assert resp_owner.status_code == 200
        assert resp_owner.json()["status"] == "cancelled"


def test_token_encryption_at_rest():
    """Verify that Fernet encryption protects tokens at rest and decrypts accurately."""
    raw_token = "google_refresh_token_very_secret_12345"
    encrypted = encrypt_token(raw_token)

    assert encrypted != raw_token
    assert "secret" not in encrypted

    decrypted = decrypt_token(encrypted)
    assert decrypted == raw_token

    # Test fallback for unencrypted legacy tokens
    legacy_mock = "mock_legacy_plain_token"
    assert decrypt_token(legacy_mock) == legacy_mock
