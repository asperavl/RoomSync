import React, { useState } from "react";
import { RefreshCw } from "lucide-react";

export default function SyncStatusBar({ onSyncComplete, notify }) {
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(new Date());

  const handleManualSync = async () => {
    setIsSyncing(true);
    try {
      const token = localStorage.getItem("roomsync_jwt");
      const headers = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("/api/sync", {
        method: "POST",
        headers,
      });
      const data = await res.json();
      setLastSyncTime(new Date());
      if (data.summary) {
        notify(`Sync complete: ${data.summary.synced} events synchronized.`);
      }
      if (onSyncComplete) onSyncComplete();
    } catch (err) {
      notify("Calendar sync connection error", "error");
    } finally {
      setIsSyncing(false);
    }
  };

  const formattedTime = lastSyncTime.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.35rem",
          fontSize: "0.75rem",
          color: "var(--text-muted)",
          padding: "0.2rem 0.4rem",
        }}
        title={`Google Calendar background sync. Last synced: ${formattedTime}`}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            backgroundColor: "var(--accent-emerald)",
          }}
          aria-hidden="true"
        />
        <span>Synced</span>
      </div>

      <button
        type="button"
        className="btn btn-ghost btn-icon"
        style={{ width: 28, height: 28, padding: 4 }}
        onClick={handleManualSync}
        disabled={isSyncing}
        aria-label={isSyncing ? "Synchronizing with Google Calendar..." : "Sync now"}
        title={`Sync with Google Calendar (last: ${formattedTime})`}
      >
        <RefreshCw size={12} className={isSyncing ? "spin" : ""} aria-hidden="true" />
      </button>
    </div>
  );
}
