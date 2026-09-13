import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Calendar as CalendarIcon,
  DoorOpen,
  Tv,
  CheckCircle2,
  AlertCircle,
  Clock,
  LogOut,
  ChevronRight,
  ArrowRight,
} from "lucide-react";

import CalendarView from "./components/CalendarView";
import BookingModal from "./components/BookingModal";
import MyBookings from "./components/MyBookings";
import SyncStatusBar from "./components/SyncStatusBar";

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);

  const [resources, setResources] = useState([]);
  const [selectedResource, setSelectedResource] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [resourceFilter, setResourceFilter] = useState("all"); // 'all' | 'room' | 'equipment'

  const [modalOpen, setModalOpen] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [activeTab, setActiveTab] = useState("calendar");
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, []);

  // Authentication check: supports URL fragment (#token=...) to avoid logging tokens
  useEffect(() => {
    let tokenFromUrl = null;
    if (window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      tokenFromUrl = hashParams.get("token");
    }
    if (!tokenFromUrl && window.location.search) {
      const queryParams = new URLSearchParams(window.location.search);
      tokenFromUrl = queryParams.get("token");
    }

    if (tokenFromUrl) {
      localStorage.setItem("roomsync_jwt", tokenFromUrl);
      window.history.replaceState({}, document.title, window.location.pathname);
      showToast("Signed in with Google Workspace.");
    }

    const savedToken = localStorage.getItem("roomsync_jwt");
    if (savedToken) {
      fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${savedToken}` },
      })
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error("Session expired");
        })
        .then((user) => {
          setCurrentUser(user);
        })
        .catch(() => {
          localStorage.removeItem("roomsync_jwt");
          setCurrentUser(null);
        })
        .finally(() => setLoadingAuth(false));
    } else {
      setLoadingAuth(false);
    }
  }, [showToast]);

  const fetchResources = useCallback(async () => {
    try {
      const res = await fetch("/api/resources");
      const data = await res.json();
      setResources(data);
      if (data.length > 0 && !selectedResource) {
        setSelectedResource(data[0]);
      }
    } catch (err) {
      showToast("Backend connection unavailable", "error");
    }
  }, [selectedResource, showToast]);

  const fetchBookings = useCallback(async () => {
    try {
      const res = await fetch("/api/bookings");
      const data = await res.json();
      setBookings(data);
    } catch (err) {
      console.error("Failed to load bookings", err);
    }
  }, []);

  useEffect(() => {
    if (currentUser) {
      fetchResources();
      fetchBookings();
    }
  }, [currentUser, fetchResources, fetchBookings]);

  const handleSignInGoogle = () => {
    window.location.href = "http://localhost:8000/api/auth/google/authorize";
  };

  const handleDemoSignIn = async () => {
    try {
      const res = await fetch("/api/auth/demo", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("roomsync_jwt", data.token);
        setCurrentUser(data.user);
        showToast(`Active session: ${data.user.name}`);
      } else {
        showToast("Demo sign-in unavailable", "error");
      }
    } catch (err) {
      showToast("Demo service offline", "error");
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem("roomsync_jwt");
    setCurrentUser(null);
    showToast("Signed out successfully.");
  };

  const handleSlotSelect = (slot) => {
    setSelectedSlot(slot);
    setModalOpen(true);
  };

  const handleBookingSuccess = () => {
    fetchBookings();
  };

  // Compute live availability status for each resource right now
  const resourceStatuses = useMemo(() => {
    const now = new Date();
    const map = {};

    resources.forEach((res) => {
      const activeBooking = bookings.find((b) => {
        if (b.resource_id !== res.id || b.status !== "confirmed") return false;
        const start = new Date(b.start_time);
        const end = new Date(b.end_time);
        return now >= start && now < end;
      });

      if (activeBooking) {
        const endTime = new Date(activeBooking.end_time).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        map[res.id] = { available: false, label: `In use until ${endTime}` };
      } else {
        map[res.id] = { available: true, label: "Available now" };
      }
    });

    return map;
  }, [resources, bookings]);

  // Filtered resources by category
  const filteredResources = useMemo(() => {
    if (resourceFilter === "all") return resources;
    return resources.filter((r) => r.type === resourceFilter);
  }, [resources, resourceFilter]);

  if (loadingAuth) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-canvas)", color: "var(--text-muted)" }}>
        <span style={{ fontSize: "0.85rem", fontVariantNumeric: "tabular-nums" }}>Connecting to RoomSync...</span>
      </div>
    );
  }

  // Authentic, high-trust corporate sign-in screen
  if (!currentUser) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-header">
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <div className="brand-icon" style={{ width: 28, height: 28 }}>
                <CalendarIcon size={16} aria-hidden="true" />
              </div>
              <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>RoomSync</span>
            </div>
            <h1>Workspace Sign In</h1>
            <p>Select your corporate Google account to manage rooms and view schedule availability.</p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <button
              onClick={handleSignInGoogle}
              className="btn btn-primary"
              style={{
                width: "100%",
                padding: "0.65rem",
                background: "#ffffff",
                color: "#18181b",
                fontWeight: 600,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              <span>Continue with Google</span>
            </button>

            <button
              onClick={handleDemoSignIn}
              className="btn btn-secondary"
              style={{ width: "100%", padding: "0.6rem", fontSize: "0.8rem" }}
            >
              <span>Sign in with Demo Credentials</span>
              <ArrowRight size={13} aria-hidden="true" />
            </button>
          </div>

          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.85rem", lineHeight: 1.4 }}>
            Direct calendar synchronization guarantees reservation availability without manual coordination.
          </div>
        </div>
      </div>
    );
  }

  const userInitial = currentUser.name ? currentUser.name.charAt(0).toUpperCase() : "U";

  return (
    <div className="app-container">
      {/* Top Navbar - Linear Grade Header */}
      <header className="navbar">
        <div className="nav-left">
          <div className="nav-brand">
            <div className="brand-icon">
              <CalendarIcon size={14} aria-hidden="true" />
            </div>
            <span className="brand-title">RoomSync</span>
          </div>

          <div className="nav-divider" aria-hidden="true" />

          <nav className="nav-breadcrumbs" aria-label="Breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={12} aria-hidden="true" />
            <span>Resources</span>
            {selectedResource && (
              <>
                <ChevronRight size={12} aria-hidden="true" />
                <span className="active">{selectedResource.name}</span>
              </>
            )}
          </nav>
        </div>

        <div className="nav-actions">
          <SyncStatusBar onSyncComplete={fetchBookings} notify={showToast} />

          {/* User profile */}
          <div className="user-badge">
            <div className="user-avatar" aria-hidden="true">
              {userInitial}
            </div>
            <span className="user-name">{currentUser.name}</span>
          </div>

          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={handleSignOut}
            aria-label="Sign out of RoomSync"
            title="Sign out"
          >
            <LogOut size={15} aria-hidden="true" />
          </button>
        </div>
      </header>

      {/* Workspace Grid */}
      <div className="workspace-grid">
        {/* Left Rail */}
        <aside className="sidebar-rail" aria-label="Resource selection rail">
          <div className="sidebar-header">
            {/* View Switcher */}
            <div className="view-tabs" role="tablist" aria-label="View options">
              <button
                type="button"
                className={`tab-btn ${activeTab === "calendar" ? "active" : ""}`}
                role="tab"
                aria-selected={activeTab === "calendar"}
                onClick={() => setActiveTab("calendar")}
              >
                <CalendarIcon size={13} aria-hidden="true" />
                <span>Calendar</span>
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === "my-bookings" ? "active" : ""}`}
                role="tab"
                aria-selected={activeTab === "my-bookings"}
                onClick={() => setActiveTab("my-bookings")}
              >
                <Clock size={13} aria-hidden="true" />
                <span>My Bookings</span>
              </button>
            </div>
          </div>

          {/* Resource Filter */}
          <div className="filter-bar" role="group" aria-label="Filter resource by type">
            <button
              type="button"
              className={`filter-chip ${resourceFilter === "all" ? "active" : ""}`}
              onClick={() => setResourceFilter("all")}
            >
              All ({resources.length})
            </button>
            <button
              type="button"
              className={`filter-chip ${resourceFilter === "room" ? "active" : ""}`}
              onClick={() => setResourceFilter("room")}
            >
              Rooms
            </button>
            <button
              type="button"
              className={`filter-chip ${resourceFilter === "equipment" ? "active" : ""}`}
              onClick={() => setResourceFilter("equipment")}
            >
              Equipment
            </button>
          </div>

          {/* Resource List */}
          <div className="resource-rail-list" role="region" aria-label="Resource list">
            {filteredResources.map((res) => {
              const isSelected = selectedResource?.id === res.id;
              const status = resourceStatuses[res.id] || { available: true, label: "Available" };

              return (
                <button
                  type="button"
                  key={res.id}
                  className={`resource-card ${isSelected ? "active" : ""}`}
                  aria-pressed={isSelected}
                  onClick={() => {
                    setSelectedResource(res);
                    setActiveTab("calendar");
                  }}
                >
                  <div className="resource-row-top">
                    <span className="resource-name">{res.name}</span>
                    <span
                      className={`resource-status-badge ${status.available ? "available" : "busy"}`}
                    >
                      <span className="resource-status-dot" aria-hidden="true" />
                      <span>{status.label}</span>
                    </span>
                  </div>

                  <div className="resource-row-meta">
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                      {res.type === "room" ? <DoorOpen size={11} aria-hidden="true" /> : <Tv size={11} aria-hidden="true" />}
                      <span>{res.type === "room" ? "Meeting Room" : "AV Resource"}</span>
                    </span>
                    {res.capacity && <span className="resource-pill">• {res.capacity} seats</span>}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Central Stage */}
        <main className="calendar-stage">
          {activeTab === "calendar" ? (
            <CalendarView
              resource={selectedResource}
              bookings={bookings}
              onSelectSlot={handleSlotSelect}
            />
          ) : (
            <MyBookings
              bookings={bookings}
              resources={resources}
              currentUser={currentUser}
              onBookingCancelled={fetchBookings}
              notify={showToast}
            />
          )}
        </main>
      </div>

      {/* Booking Modal Sheet */}
      {currentUser && (
        <BookingModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          selectedSlot={selectedSlot}
          resource={selectedResource}
          user={currentUser}
          onBookingSuccess={handleBookingSuccess}
          notify={showToast}
        />
      )}

      {/* Toasts */}
      {toast && (
        <div className="toast-container" role="status" aria-live="polite">
          <div className="toast-item">
            {toast.type === "error" ? (
              <AlertCircle size={15} color="var(--accent-rose)" aria-hidden="true" />
            ) : (
              <CheckCircle2 size={15} color="var(--accent-emerald)" aria-hidden="true" />
            )}
            <span>{toast.message}</span>
          </div>
        </div>
      )}
    </div>
  );
}
