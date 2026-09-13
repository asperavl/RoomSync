import React, { useState, useEffect, useRef } from "react";
import { X, AlertTriangle, Video, Users } from "lucide-react";

export default function BookingModal({
  isOpen,
  onClose,
  selectedSlot,
  resource,
  user,
  onBookingSuccess,
  notify,
}) {
  const modalRef = useRef(null);
  const titleInputRef = useRef(null);

  const [title, setTitle] = useState("");
  const [attendeesInput, setAttendeesInput] = useState("");
  const [addGoogleMeet, setAddGoogleMeet] = useState(false);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [selectedDuration, setSelectedDuration] = useState(30);
  const [loading, setLoading] = useState(false);
  const [ruleWarning, setRuleWarning] = useState("");
  const [conflictError, setConflictError] = useState("");

  const toLocalISO = (date) => {
    if (!date) return "";
    const pad = (n) => String(n).padStart(2, "0");
    const d = new Date(date);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  useEffect(() => {
    if (selectedSlot && resource) {
      const startIso = toLocalISO(selectedSlot.start);
      const endIso = toLocalISO(selectedSlot.end);
      setStartTime(startIso);
      setEndTime(endIso);
      setTitle(`${resource.name} Reservation`);
      setAttendeesInput("");
      setAddGoogleMeet(resource.type === "room");
      setConflictError("");

      if (selectedSlot.start && selectedSlot.end) {
        const diffMinutes = Math.round((new Date(selectedSlot.end) - new Date(selectedSlot.start)) / 60000);
        setSelectedDuration(diffMinutes > 0 ? diffMinutes : 30);
      }
    }
  }, [selectedSlot, resource]);

  // Set duration helper
  const handleSetDuration = (minutes) => {
    setSelectedDuration(minutes);
    if (!startTime) return;
    const start = new Date(startTime);
    const newEnd = new Date(start.getTime() + minutes * 60000);
    setEndTime(toLocalISO(newEnd));
  };

  // Keyboard navigation: Escape to cancel, Ctrl/Cmd + Enter to submit
  useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(() => {
      if (titleInputRef.current) {
        titleInputRef.current.focus();
        titleInputRef.current.select();
      }
    }, 50);

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        const submitBtn = modalRef.current?.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.click();
        return;
      }

      // Focus trap
      if (e.key === "Tab" && modalRef.current) {
        const focusables = modalRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Notice period warning check
  useEffect(() => {
    if (!startTime || !resource) return;
    const now = new Date();
    const start = new Date(startTime);
    const diffMinutes = Math.floor((start - now) / 60000);

    if (diffMinutes < resource.min_notice_minutes) {
      setRuleWarning(
        `Notice policy requires at least ${resource.min_notice_minutes}m advance booking. (Selected: ${diffMinutes}m)`
      );
    } else {
      setRuleWarning("");
    }
  }, [startTime, resource]);

  if (!isOpen || !resource) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setConflictError("");

    const start = new Date(startTime);
    const end = new Date(endTime);

    if (end <= start) {
      setConflictError("End time must be after start time.");
      setLoading(false);
      return;
    }

    const attendeeEmails = attendeesInput
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && s.includes("@"));

    try {
      const token = localStorage.getItem("roomsync_jwt");
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("/api/bookings", {
        method: "POST",
        headers,
        body: JSON.stringify({
          resource_id: resource.id,
          user_id: user.id,
          title: title || `${resource.name} Reservation`,
          attendees: attendeeEmails,
          add_google_meet: addGoogleMeet,
          start_time: start.toISOString(),
          end_time: end.toISOString(),
        }),
      });

      const data = await res.json();

      if (res.status === 409) {
        setConflictError(
          "Schedule collision: this time slot was just booked by another attendee. Please select an adjacent free slot."
        );
        notify("Schedule conflict: slot unavailable", "error");
      } else if (res.status === 400) {
        setConflictError(data.detail?.message || "Booking violates workplace policy.");
        notify("Policy constraint violated", "error");
      } else if (!res.ok) {
        setConflictError("Unable to complete reservation. Please retry.");
      } else {
        const attendeeCount = attendeeEmails.length;
        const msg = attendeeCount > 0 ? ` (${attendeeCount} coworkers invited)` : "";
        notify(`Reserved ${resource.name}${msg}.`);
        onBookingSuccess(data);
        onClose();
      }
    } catch (err) {
      setConflictError("Network connection error communicating with booking service.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-booking-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2 id="modal-booking-title" className="modal-title">
              Reserve {resource.name}
            </h2>
            <div className="modal-subtitle">
              {resource.type === "room" ? "Meeting Room" : "AV Equipment"}
              {resource.capacity ? ` • ${resource.capacity} seats` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-icon"
            aria-label="Close dialog"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {/* Title */}
            <div className="form-field">
              <label htmlFor="modal-title-input" className="field-label">
                Meeting Subject
              </label>
              <input
                id="modal-title-input"
                ref={titleInputRef}
                className="field-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Design Systems Sync"
                required
              />
            </div>

            {/* Duration Quick Selector */}
            <div className="form-field">
              <label className="field-label">Duration</label>
              <div className="duration-chips">
                {[15, 30, 45, 60, 90].map((mins) => (
                  <button
                    key={mins}
                    type="button"
                    className={`duration-chip ${selectedDuration === mins ? "active" : ""}`}
                    onClick={() => handleSetDuration(mins)}
                  >
                    {mins < 60 ? `${mins}m` : `${mins / 60}h`}
                  </button>
                ))}
              </div>
            </div>

            {/* Time Pickers */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div className="form-field">
                <label htmlFor="modal-start-time" className="field-label">
                  Start Time
                </label>
                <input
                  id="modal-start-time"
                  type="datetime-local"
                  className="field-input"
                  value={startTime}
                  onChange={(e) => {
                    setStartTime(e.target.value);
                    if (e.target.value && selectedDuration) {
                      const start = new Date(e.target.value);
                      const newEnd = new Date(start.getTime() + selectedDuration * 60000);
                      setEndTime(toLocalISO(newEnd));
                    }
                  }}
                  required
                />
              </div>

              <div className="form-field">
                <label htmlFor="modal-end-time" className="field-label">
                  End Time
                </label>
                <input
                  id="modal-end-time"
                  type="datetime-local"
                  className="field-input"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  required
                />
              </div>
            </div>

            {/* Coworker Invites for rooms */}
            {resource.type === "room" && (
              <div className="form-field">
                <label htmlFor="modal-attendees-input" className="field-label" style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <Users size={12} color="var(--text-muted)" aria-hidden="true" />
                  <span>Coworkers (comma-separated emails)</span>
                </label>
                <input
                  id="modal-attendees-input"
                  className="field-input"
                  value={attendeesInput}
                  onChange={(e) => setAttendeesInput(e.target.value)}
                  placeholder="sarah@company.com, alex@company.com"
                />
              </div>
            )}

            {/* Google Meet Toggle */}
            {resource.type === "room" && (
              <label
                htmlFor="modal-meet-toggle"
                style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.78rem", color: "var(--text-secondary)" }}
              >
                <input
                  id="modal-meet-toggle"
                  type="checkbox"
                  checked={addGoogleMeet}
                  onChange={(e) => setAddGoogleMeet(e.target.checked)}
                  style={{ accentColor: "var(--accent-primary)", width: 14, height: 14 }}
                />
                <Video size={14} color="var(--text-muted)" aria-hidden="true" />
                <span>Attach Google Meet video room link</span>
              </label>
            )}

            {/* Inline Warnings & Errors */}
            {ruleWarning && (
              <div className="callout callout-warning" role="alert">
                <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                <span>{ruleWarning}</span>
              </div>
            )}

            {conflictError && (
              <div className="callout callout-error" role="alert">
                <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                <span>{conflictError}</span>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <span className="modal-footer-hint">⌘ + Enter to confirm</span>
            <div className="modal-footer-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Checking Availability..." : "Confirm Booking"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
