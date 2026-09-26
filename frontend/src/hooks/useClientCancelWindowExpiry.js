import { useEffect, useState } from "react";
import { msUntilNextClientCancelExpiry } from "@/lib/hearingLifecycle";

// setTimeout overflows past ~24.8 days; windows are 1 hour, this is a guard.
const MAX_TIMEOUT_MS = 2147483647;
// Fire just after the deadline so the re-render sees the window as closed
// (the backend treats exactly payment_confirmed_at + 1h as already closed).
const DEADLINE_SLACK_MS = 50;

/* Re-render trigger: callers keep calling getHearingPermissions(h, user) as
   usual (it reads the clock at render time); this hook only makes sure a
   render happens when a window closes. Schedules ONE timeout for the soonest open client cancellation window among
   `hearings` and bumps `now` when it closes — so a page left open drops its
   Cancel button and shows the expiry message without a refresh, without
   re-rendering every second. Reschedules for the next window after each fire;
   clears on unmount or when the hearings change. Also refreshes when the tab
   becomes visible again, since background tabs can delay timers.
   Display only — the backend enforces the window on its own clock. */
export default function useClientCancelWindowExpiry(hearings, user) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const ms = msUntilNextClientCancelExpiry(hearings, user, Date.now());
    if (ms === null) return undefined;
    const timer = setTimeout(() => setNow(Date.now()), Math.min(ms + DEADLINE_SLACK_MS, MAX_TIMEOUT_MS));
    return () => clearTimeout(timer);
  }, [hearings, user, now]);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const onVisible = () => { if (document.visibilityState === "visible") setNow(Date.now()); };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  return now;
}
