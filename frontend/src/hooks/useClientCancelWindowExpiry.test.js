import React from "react";
import { createRoot } from "react-dom/client";
import useClientCancelWindowExpiry from "@/hooks/useClientCancelWindowExpiry";
import { getHearingPermissions, CLIENT_CANCEL_WINDOW_MS } from "@/lib/hearingLifecycle";

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const START = Date.parse("2026-08-16T06:00:00.000Z");
const client = { user_id: "user_client" };

// Renders what the list/dialog render: Cancel while canCancel, the expiry
// message once cancelWindowExpired — driven only by the hook's re-render.
function Probe({ hearing, user }) {
  const hearings = React.useMemo(() => [hearing], [hearing]);
  useClientCancelWindowExpiry(hearings, user);
  const p = getHearingPermissions(hearing, user);
  return (
    <div>
      {p.canCancel && <button data-testid="cancel">Cancel</button>}
      {p.cancelWindowExpired && <p data-testid="expired">expired</p>}
    </div>
  );
}

let container;
let root;
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(START);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.useRealTimers();
});

const paidMinutesAgo = (minutes) => ({
  requesting_user_id: client.user_id,
  status: "broadcast",
  payment_confirmed_at: new Date(START - minutes * 60 * 1000).toISOString(),
});
const q = (id) => container.querySelector(`[data-testid="${id}"]`);

test("A-C: Cancel visible, then disappears and the message appears at the deadline without a refresh", () => {
  act(() => root.render(<Probe hearing={paidMinutesAgo(50)} user={client} />));
  expect(q("cancel")).not.toBeNull();
  expect(q("expired")).toBeNull();

  act(() => { jest.advanceTimersByTime(10 * 60 * 1000 - 1000); }); // 1s before the deadline
  expect(q("cancel")).not.toBeNull();

  act(() => { jest.advanceTimersByTime(1000 + 100); }); // past deadline + slack
  expect(q("cancel")).toBeNull();
  expect(q("expired")).not.toBeNull();
  expect(jest.getTimerCount()).toBe(0); // nothing left scheduled once every window closed
});

test("schedules a single timeout, not a per-second tick", () => {
  act(() => root.render(<Probe hearing={paidMinutesAgo(1)} user={client} />));
  expect(jest.getTimerCount()).toBe(1);
  act(() => { jest.advanceTimersByTime(30 * 60 * 1000); });
  expect(jest.getTimerCount()).toBe(1);
  expect(q("cancel")).not.toBeNull();
});

test("D: timer cleared on unmount — no orphaned timeout", () => {
  act(() => root.render(<Probe hearing={paidMinutesAgo(30)} user={client} />));
  expect(jest.getTimerCount()).toBe(1);
  act(() => root.unmount());
  expect(jest.getTimerCount()).toBe(0);
  root = createRoot(container); // afterEach unmounts again
});

test("E/F/G: no timer for cancelled, non-requester (admin/counsel) or missing payment time", () => {
  const cases = [
    [{ ...paidMinutesAgo(10), status: "cancelled" }, client],
    [paidMinutesAgo(10), { user_id: "user_admin", role: "admin" }],
    [paidMinutesAgo(10), { user_id: "user_counsel" }],
    [{ ...paidMinutesAgo(10), payment_confirmed_at: null }, client],
  ];
  for (const [hearing, user] of cases) {
    act(() => root.render(<Probe hearing={hearing} user={user} />));
    expect(jest.getTimerCount()).toBe(0);
    expect(q("cancel")).toBeNull();
  }
});

test("already-expired window on first render — message, no Cancel, no timer", () => {
  act(() => root.render(<Probe hearing={paidMinutesAgo(CLIENT_CANCEL_WINDOW_MS / 60000 + 5)} user={client} />));
  expect(q("cancel")).toBeNull();
  expect(q("expired")).not.toBeNull();
  expect(jest.getTimerCount()).toBe(0);
});
