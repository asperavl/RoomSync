# RoomSync

> Conflict-safe workspace resource scheduling with two-way Google Calendar synchronization.

RoomSync eliminates meeting room double-bookings and scheduling friction. Built with PostgreSQL GiST exclusion constraints at the database layer, it guarantees zero overlapping reservations while keeping personal and resource calendars in sync.

---

## Features

- **Conflict-Safe Scheduling**: Enforces non-overlapping time ranges (`tstzrange`) directly in PostgreSQL via GiST exclusion constraints.
- **Two-Way Google Calendar Sync**: Automatic background synchronization between RoomSync reservations and Google Calendar events.
- **Linear-Grade Interface**: Clean, dark-mode calendar grid built with React, FullCalendar, and quick duration presets.
- **Live Availability Tracking**: Real-time room status indicators (`Available now` / `In use until...`).
- **Secure by Default**: JWT session management, Fernet AES token encryption at rest, CSRF state nonces, and strict ownership checks (IDOR protection).

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy (Async), PostgreSQL + `btree_gist`
- **Frontend**: React 18, Vite, FullCalendar, Lucide Icons, Vanilla CSS
- **Authentication & Security**: OAuth 2.0 (Google), PyJWT, Cryptography (Fernet AES)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally with `btree_gist` enabled

### 1. Database Setup

```sql
CREATE DATABASE roomsync;
\c roomsync
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL, JWT_SECRET_KEY, and Google OAuth credentials

# Initialize tables and seed sample rooms
python scripts/init_db.py

# Start FastAPI server
python -m uvicorn backend.app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000` (docs at `/docs`).

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The application will be running at `http://localhost:5173`.

---

## Running Tests

Run the full automated test suite (unit, concurrency, constraints, and security):

```bash
pytest
```

---

## License

MIT
