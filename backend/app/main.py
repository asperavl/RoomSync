import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import get_db, init_db, async_session_factory
from backend.app.models import Resource, User, Booking
from backend.app.schemas import (
    ResourceCreate,
    ResourceResponse,
    UserCreate,
    UserResponse,
    BookingCreate,
    BookingResponse,
    CancelBookingRequest,
)
from backend.app.services.booking_service import (
    create_booking_constraint_protected,
    create_booking_naive_check_then_insert,
    cancel_booking,
    BookingConflictError,
    ResourceNotFoundError,
    BookingNotFoundError,
)
from backend.app.services.google_sync import (
    sync_pending_bookings,
    sync_single_booking_with_retry,
    get_google_oauth_url,
    exchange_google_code,
    get_google_user_info,
    delete_google_calendar_event,
    run_periodic_sync_worker,
    encrypt_token,
    decrypt_token,
)
from backend.app.auth import create_access_token, get_current_user
from backend.app.validation import BusinessRuleViolation

_last_sync_timestamp = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        print(f"Database init warning (expected during isolated unit tests): {e}")

    sync_task = asyncio.create_task(
        run_periodic_sync_worker(
            session_factory=async_session_factory,
            interval_seconds=settings.SYNC_INTERVAL_SECONDS,
        )
    )

    yield

    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="RoomSync API",
    description="Conflict-safe shared resource booking system with live Google Calendar sync",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(BusinessRuleViolation)
async def handle_business_rule_violation(request, exc: BusinessRuleViolation):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "business_rule_violation", "message": exc.message, "rule": exc.rule_name},
    )


@app.exception_handler(BookingConflictError)
async def handle_booking_conflict(request, exc: BookingConflictError):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "booking_conflict", "message": exc.message},
    )


@app.exception_handler(ResourceNotFoundError)
async def handle_resource_not_found(request, exc: ResourceNotFoundError):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "resource_not_found", "message": str(exc)},
    )


@app.exception_handler(BookingNotFoundError)
async def handle_booking_not_found(request, exc: BookingNotFoundError):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "booking_not_found", "message": str(exc)},
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "RoomSync"}


# Resources
@app.post("/api/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: ResourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resource = Resource(**data.model_dump())
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


@app.get("/api/resources", response_model=List[ResourceResponse])
async def list_resources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resource))
    return result.scalars().all()


# Users & Current Profile
@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = User(**data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at,
        google_connected=bool(user.google_refresh_token),
    )


@app.get("/api/users", response_model=List[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id,
            name=u.name,
            email=u.email,
            created_at=u.created_at,
            google_connected=bool(u.google_refresh_token),
        )
        for u in users
    ]


@app.get("/api/auth/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Returns currently authenticated user profile from JWT session."""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "google_connected": bool(current_user.google_refresh_token),
    }


@app.post("/api/auth/demo")
async def demo_login(db: AsyncSession = Depends(get_db)):
    """Issues signed JWT token for first available demo employee in non-production."""
    if settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Demo login disabled in production")
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    if not users:
        raise HTTPException(status_code=404, detail="No demo users available")
    demo_user = users[0]
    token = create_access_token({
        "sub": str(demo_user.id),
        "email": demo_user.email,
        "name": demo_user.name,
    })
    return {
        "token": token,
        "user": {
            "id": demo_user.id,
            "name": demo_user.name,
            "email": demo_user.email,
            "google_connected": bool(demo_user.google_refresh_token),
        },
    }


# Google OAuth 2.0 Endpoints
@app.get("/api/auth/google/authorize")
async def google_authorize(redirect: bool = Query(True)):
    """
    Kicks off Google OAuth 2.0 flow with random cryptographic state nonce for CSRF mitigation.
    """
    state_nonce = secrets.token_urlsafe(32)
    auth_url = get_google_oauth_url(state=state_nonce)
    response = RedirectResponse(url=auth_url) if redirect else JSONResponse({"auth_url": auth_url, "state": state_nonce})
    response.set_cookie(
        key="oauth_state",
        value=state_nonce,
        httponly=True,
        samesite="lax",
        secure=(settings.ENVIRONMENT == "production"),
        max_age=600,
    )
    return response


@app.get("/api/auth/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    OAuth 2.0 Callback:
    Validates cryptographic state nonce to prevent login CSRF,
    encrypts refresh tokens at rest, and redirects using safe URL fragments.
    """
    stored_state = request.cookies.get("oauth_state")
    if stored_state and state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state parameter. Potential CSRF detected.")

    tokens = await exchange_google_code(code)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    # Fetch user details from Google
    user_info = await get_google_user_info(access_token)
    email = user_info["email"]
    name = user_info.get("name") or email.split("@")[0].capitalize()

    # Find or create user
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()

    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    if user:
        if encrypted_refresh:
            user.google_refresh_token = encrypted_refresh
        user.name = name
    else:
        user = User(name=name, email=email, google_refresh_token=encrypted_refresh)
        db.add(user)

    await db.commit()
    await db.refresh(user)

    # Issue JWT session token
    jwt_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
    })

    # URL fragment (#token=...) prevents token leaking in server access logs and HTTP Referer headers
    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/#token={jwt_token}&google_connected=true")
    response.delete_cookie("oauth_state")
    return response


@app.post("/api/auth/google/disconnect")
async def google_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnects Google Calendar for the authenticated user."""
    current_user.google_refresh_token = None
    await db.commit()
    return {"status": "disconnected"}


# Bookings
@app.post("/api/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    data: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Constraint-protected booking creation. Bound strictly to authenticated user identity."""
    data.user_id = current_user.id
    booking = await create_booking_constraint_protected(session=db, data=data)

    # Try immediate sync to Google Calendar if user has connected their account
    try:
        await sync_single_booking_with_retry(
            session=db,
            booking=booking,
            max_retries=1,
            attendees=data.attendees,
            add_google_meet=data.add_google_meet,
        )
    except Exception as e:
        print(f"[Calendar Sync] Initial sync deferred to background worker: {e}")

    return booking


@app.post("/api/bookings/naive", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking_naive(data: BookingCreate, db: AsyncSession = Depends(get_db)):
    """Naive check-then-insert booking endpoint for race condition benchmarking (development only)."""
    if settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Naive benchmarking endpoint disabled in production.")
    booking = await create_booking_naive_check_then_insert(session=db, data=data)
    return booking


@app.post("/api/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_existing_booking(
    booking_id: int,
    request_data: CancelBookingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enforces cancellation window rule and deletes the event from Google Calendar."""
    b_result = await db.execute(select(Booking).where(Booking.id == booking_id))
    existing_booking = b_result.scalar_one_or_none()
    if not existing_booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if existing_booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission Denied: Only the employee who reserved this slot can cancel it.",
        )

    # If already synced to Google Calendar, delete live event
    google_event_id = existing_booking.google_event_id

    booking = await cancel_booking(
        session=db,
        booking_id=booking_id,
        user_id=current_user.id,
        reason=request_data.reason,
    )

    if google_event_id:
        user_res = await db.execute(select(User).where(User.id == current_user.id))
        user = user_res.scalar_one_or_none()
        if user and user.google_refresh_token:
            asyncio.create_task(
                delete_google_calendar_event(
                    refresh_token=user.google_refresh_token,
                    event_id=google_event_id,
                )
            )

    return booking


@app.get("/api/bookings", response_model=List[BookingResponse])
async def list_bookings(
    resource_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Booking)
    if resource_id:
        query = query.where(Booking.resource_id == resource_id)
    if user_id:
        query = query.where(Booking.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


# Manual Sync Trigger (Authenticated & Debounced)
@app.post("/api/sync")
async def trigger_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Triggers immediate synchronization pass for all pending bookings."""
    global _last_sync_timestamp
    loop = asyncio.get_event_loop()
    now = loop.time()
    if now - _last_sync_timestamp < 10.0:
        return {"status": "debounced", "message": "Sync was triggered recently. Please wait a few seconds."}

    _last_sync_timestamp = now
    summary = await sync_pending_bookings(session=db)
    return {"status": "success", "summary": summary}
