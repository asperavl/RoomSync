import React from "react";
import { Trash2 } from "lucide-react";

export default function MyBookings({
  bookings,
  resources,
  currentUser,
  onBookingCancelled,
  notify,
}) {
  const userBookings = bookings.filter((b) => b.user_id === currentUser?.id);
  const resourceMap = Object.fromEntries(resources.map((r) => [r.id, r]));

  const handleCancel = async (booking) => {
    const res = resourceMap[booking.resource_id];
    const windowMinutes = res ? res.cancellation_window_minutes : 15;

    if (!window.confirm(`Cancel reservation "${booking.title || 'Room'}"? (Must be cancelled ≥ ${windowMinutes}m before start).`)) {
      return;
    }

    try {
      const token = localStorage.getItem("roomsync_jwt");
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(`/api/bookings/${booking.id}/cancel`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          user_id: currentUser.id,
          reason: "Cancelled by employee from dashboard",
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        notify(data.detail?.message || "Cancellation rejected by policy.", "error");
      } else {
        notify("Booking cancelled successfully.");
        if (onBookingCancelled) onBookingCancelled();
      }
    } catch (err) {
      notify("Network error during cancellation.", "error");
    }
  };

  const formatDate = (dateStr) => {
    const d = new Date(dateStr);
    return d.toLocaleString([], {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 860 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: "1.05rem", fontWeight: 600, color: "var(--text-primary)" }}>
          My Reservations
        </h1>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          {userBookings.length} total
        </span>
      </div>

      {userBookings.length === 0 ? (
        <div
          style={{
            padding: "3rem 1rem",
            textAlign: "center",
            background: "var(--bg-surface)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            No active reservations found.
          </p>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Select a room or equipment from the sidebar to schedule your first reservation.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {userBookings.map((b) => {
            const res = resourceMap[b.resource_id];
            const isCancelled = b.status === "cancelled";
            const isSynced = Boolean(b.google_event_id);

            return (
              <div
                key={b.id}
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-subtle)",
                  opacity: isCancelled ? 0.6 : 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                      {b.title || "Reservation"}
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "var(--accent-primary)", fontWeight: 500 }}>
                      • {res ? res.name : `Resource #${b.resource_id}`}
                    </span>
                  </div>

                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                    {formatDate(b.start_time)} → {formatDate(b.end_time)}
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexShrink: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem", color: isSynced ? "var(--accent-emerald)" : "var(--accent-amber)" }}>
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        backgroundColor: isSynced ? "var(--accent-emerald)" : "var(--accent-amber)",
                      }}
                      aria-hidden="true"
                    />
                    <span>{isCancelled ? "Cancelled" : isSynced ? "Synced to Calendar" : "Sync Pending"}</span>
                  </div>

                  {!isCancelled && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.72rem", minHeight: 26 }}
                      onClick={() => handleCancel(b)}
                      aria-label={`Cancel reservation for ${b.title || 'room'}`}
                    >
                      <Trash2 size={12} aria-hidden="true" />
                      <span>Cancel</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
