from datetime import datetime
from typing import Optional, Literal, List
from pydantic import BaseModel, ConfigDict, model_validator, Field


class UserBase(BaseModel):
    name: str
    email: str


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime
    google_connected: bool = False

    model_config = ConfigDict(from_attributes=True)


class ResourceBase(BaseModel):
    name: str
    type: Literal["room", "equipment"]
    capacity: Optional[int] = None
    min_notice_minutes: int = 30
    cancellation_window_minutes: int = 15


class ResourceCreate(ResourceBase):
    pass


class ResourceResponse(ResourceBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    resource_id: int
    user_id: Optional[int] = None  # Populated from authenticated session
    start_time: datetime
    end_time: datetime
    title: Optional[str] = "Room Reservation"
    attendees: Optional[List[str]] = Field(default=None, max_length=50)
    add_google_meet: bool = False

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")
        return self


class BookingResponse(BaseModel):
    id: int
    resource_id: int
    user_id: int
    start_time: datetime
    end_time: datetime
    title: Optional[str] = "Room Reservation"
    google_event_id: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CancelBookingRequest(BaseModel):
    user_id: Optional[int] = None  # Authenticated user ID is derived from JWT
    reason: Optional[str] = None
