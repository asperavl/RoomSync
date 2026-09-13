# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python + FastAPI backend, PostgreSQL database, React frontend with FullCalendar, OAuth 2.0 for Google Calendar access, lightweight JWT-based session for app login, cron job for calendar syncing.

## Users

**Primary:** Employees at a mid-size company who need to book shared resources (meeting rooms, projectors, AV equipment) for a specific time. They are planning a meeting or need equipment, need instant availability confirmation, and want zero back-and-forth with an office manager or shared spreadsheet.

**Secondary:** Employees who book via Google Calendar directly and expect the resource system to stay in sync with that action.

## Product Purpose

RoomSync eliminates manual coordination overhead for shared-resource scheduling. It turns "email the office manager and hope" into an instant, conflict-safe, calendar-integrated booking. Success means: employees never double-book, never wonder if a room is free, and never maintain two separate systems — the booking and their calendar are one source of truth.

## Positioning

Conflict-safe, calendar-integrated resource booking with zero human policing. Instant confirmation with guaranteed no double-booking, automatic enforcement of operational rules (notice periods, cancellation windows), and two-way Google Calendar sync so the booking shows up where employees already look.

## Operating Context

Internal company tool (personal project). Employees check availability, book a resource for a time slot, and see it reflected on their Google Calendar automatically. Resources booked via Google Calendar directly sync back into RoomSync. An office admin may configure resources, rules, and view usage. No external-facing or multi-tenant requirements.

## Capabilities and Constraints

**Confirmed capabilities:**
- Real-time availability checking with conflict prevention (no two successful bookings for the same slot)
- Enforceable operational rules: minimum notice period for booking, cancellation windows
- Two-way Google Calendar sync via OAuth 2.0
- JWT-based session authentication for app login
- Cron-based background sync between RoomSync and Google Calendar

**Constraints:**
- Google Calendar only (no Microsoft/Outlook integration)
- Single-tenant internal deployment
- Calendar sync latency bounded by cron interval

**Undecided:**
- Admin role scope and permissions model
- Specific operational rules (how far ahead you can book, max duration, recurring bookings)
- Notification preferences (email, in-app, none)

## Evidence on Hand

No existing content, branding, testimonials, or data assets. This is a greenfield personal project. Future work must not fabricate usage statistics, company logos, or testimonials.

## Product Principles

1. **One source of truth.** A booking exists in exactly one canonical state; the calendar is a reflection, not a competitor.
2. **Conflict-safe by default.** The system prevents double-booking mechanically — no human policing, no honor system.
3. **Zero-friction booking.** Finding availability and confirming a reservation should take seconds, not a conversation.
4. **Transparent rules.** Operational constraints (notice periods, cancellation windows) are visible before you hit a wall, not after.
5. **Sync, don't duplicate.** Calendar integration means the user checks one place, not two.
