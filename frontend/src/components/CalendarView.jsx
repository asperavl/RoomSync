import React, { useRef, useMemo } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";

export default function CalendarView({
  resource,
  bookings,
  onSelectSlot,
}) {
  const calendarRef = useRef(null);

  // Memoize events mapping
  const events = useMemo(() => {
    if (!resource || !bookings) return [];
    return bookings
      .filter((b) => b.resource_id === resource.id && b.status === "confirmed")
      .map((b) => ({
        id: String(b.id),
        title: b.title || `Reserved`,
        start: b.start_time,
        end: b.end_time,
        extendedProps: {
          googleEventId: b.google_event_id,
          status: b.status,
          userId: b.user_id,
        },
      }));
  }, [bookings, resource]);

  const handleDateSelect = (selectInfo) => {
    onSelectSlot({
      start: selectInfo.start,
      end: selectInfo.end,
    });
  };

  const renderEventContent = (eventInfo) => {
    const isSynced = Boolean(eventInfo.event.extendedProps.googleEventId);
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", overflow: "hidden", padding: "1px 3px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", minWidth: 0, overflow: "hidden" }}>
          <span
            style={{
              width: 5,
              height: 5,
              borderRadius: "50%",
              backgroundColor: isSynced ? "var(--accent-emerald)" : "var(--accent-amber)",
              flexShrink: 0,
            }}
            title={isSynced ? "Synced with Google Calendar" : "Sync pending"}
            aria-hidden="true"
          />
          <span style={{ fontWeight: 600, fontSize: "0.74rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "#e2e8f0" }}>
            {eventInfo.event.title}
          </span>
        </div>
      </div>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.85rem" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
          <h1 style={{ fontSize: "1.05rem", fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
            {resource ? resource.name : "Select a Resource"}
          </h1>
          {resource && (
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              {resource.type === "room" ? "Meeting Room" : "Equipment"}
              {resource.capacity ? ` • ${resource.capacity} seats` : ""}
            </span>
          )}
        </div>

        {resource && (
          <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", fontSize: "0.72rem", color: "var(--text-muted)" }}>
            <span>Notice: {resource.min_notice_minutes}m</span>
            <span>•</span>
            <span>Cancel window: {resource.cancellation_window_minutes}m</span>
          </div>
        )}
      </div>

      <div style={{ flex: 1 }}>
        <FullCalendar
          ref={calendarRef}
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "timeGridDay,timeGridWeek,dayGridMonth",
          }}
          selectable={true}
          selectMirror={true}
          dayMaxEvents={true}
          weekends={true}
          slotMinTime="08:00:00"
          slotMaxTime="20:00:00"
          allDaySlot={false}
          select={handleDateSelect}
          events={events}
          eventContent={renderEventContent}
          height="auto"
        />
      </div>
    </div>
  );
}
