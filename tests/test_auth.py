import pytest
import time
from datetime import timedelta
from backend.app.auth import create_access_token, decode_access_token


class TestAuthJWT:
    """Unit tests for lightweight HMAC-SHA256 JWT generation and validation."""

    def test_create_and_decode_valid_token(self):
        payload = {"sub": "123", "email": "employee@company.internal", "name": "Alex"}
        token = create_access_token(payload, expires_delta=timedelta(hours=1))
        
        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "123"
        assert decoded["email"] == "employee@company.internal"
        assert decoded["name"] == "Alex"
        assert "exp" in decoded

    def test_tampered_token_signature_rejected(self):
        payload = {"sub": "123", "email": "employee@company.internal"}
        token = create_access_token(payload)
        
        # Tamper with the payload part
        parts = token.split(".")
        tampered_token = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
        
        decoded = decode_access_token(tampered_token)
        assert decoded is None

    def test_expired_token_rejected(self):
        payload = {"sub": "123", "email": "employee@company.internal"}
        # Create token that expired 10 seconds ago
        token = create_access_token(payload, expires_delta=timedelta(seconds=-10))
        
        decoded = decode_access_token(token)
        assert decoded is None

    def test_malformed_token_rejected(self):
        assert decode_access_token("not.a.valid.jwt.string") is None
        assert decode_access_token("") is None
        assert decode_access_token("abc.def") is None
