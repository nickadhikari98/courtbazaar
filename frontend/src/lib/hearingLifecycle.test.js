import {
  getHearingPermissions, msUntilNextClientCancelExpiry, CLIENT_CANCEL_WINDOW_MS,
} from "@/lib/hearingLifecycle";

const PAID_AT = "2026-08-16T05:40:43.104000+00:00";
const PAID_MS = Date.parse(PAID_AT);
const client = { user_id: "user_client", role: "advocate" };
const admin = { user_id: "user_admin", role: "admin" };
const counsel = { user_id: "user_counsel", role: "advocate" };

const paidHearing = (extra = {}) => ({
  hearing_id: "hearing_1",
  requesting_user_id: client.user_id,
  proxy_counsel_user_id: counsel.user_id,
  status: "broadcast",
  commercially_locked: true,
  payment_confirmed_at: PAID_AT,
  ...extra,
});

describe("client cancellation window (B6)", () => {
  test("A: paid hearing inside the window — Cancel visible, no expiry message", () => {
    const p = getHearingPermissions(paidHearing(), client, PAID_MS + 59 * 60 * 1000);
    expect(p.canCancel).toBe(true);
    expect(p.cancelWindowExpired).toBe(false);
  });

  test("B/C: at exactly 1 hour and after — Cancel gone, expiry message shown", () => {
    for (const offset of [CLIENT_CANCEL_WINDOW_MS, CLIENT_CANCEL_WINDOW_MS + 1, 3 * 24 * 3600 * 1000]) {
      const p = getHearingPermissions(paidHearing(), client, PAID_MS + offset);
      expect(p.canCancel).toBe(false);
      expect(p.cancelWindowExpired).toBe(true);
    }
  });

  test("window applies in every paid status, not just broadcast", () => {
    for (const status of ["accepted", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed"]) {
      expect(getHearingPermissions(paidHearing({ status }), client, PAID_MS + 1000).canCancel).toBe(true);
      expect(getHearingPermissions(paidHearing({ status }), client, PAID_MS + CLIENT_CANCEL_WINDOW_MS).canCancel).toBe(false);
    }
  });

  test("E: already cancelled hearing — Cancel unavailable, no expiry message", () => {
    const p = getHearingPermissions(paidHearing({ status: "cancelled" }), client, PAID_MS + 1000);
    expect(p.canCancel).toBe(false);
    expect(p.cancelWindowExpired).toBe(false);
  });

  test("F: admin and counsel views are not driven by the client timer", () => {
    for (const viewer of [admin, counsel]) {
      for (const offset of [1000, CLIENT_CANCEL_WINDOW_MS + 1]) {
        const p = getHearingPermissions(paidHearing(), viewer, PAID_MS + offset);
        expect(p.canCancel).toBe(false);
        expect(p.cancelWindowExpired).toBe(false);
      }
    }
    expect(msUntilNextClientCancelExpiry([paidHearing()], admin, PAID_MS + 1000)).toBeNull();
    expect(msUntilNextClientCancelExpiry([paidHearing()], counsel, PAID_MS + 1000)).toBeNull();
  });

  test("G: missing or unparseable payment_confirmed_at — client cannot cancel (fails closed)", () => {
    for (const payment_confirmed_at of [undefined, null, "", "not-a-date"]) {
      const h = paidHearing({ payment_confirmed_at });
      const p = getHearingPermissions(h, client, PAID_MS);
      expect(p.canCancel).toBe(false);
      expect(p.cancelWindowExpired).toBe(true);
      expect(msUntilNextClientCancelExpiry([h], client, PAID_MS)).toBeNull();
    }
  });

  test("unpaid behaviour unchanged: unlocked requested cancellable, locked not", () => {
    const unpaid = { requesting_user_id: client.user_id, status: "requested", payment_confirmed_at: null };
    expect(getHearingPermissions(unpaid, client).canCancel).toBe(true);
    expect(getHearingPermissions({ ...unpaid, commercially_locked: true }, client).canCancel).toBe(false);
    expect(getHearingPermissions(unpaid, client).cancelWindowExpired).toBe(false);
    expect(msUntilNextClientCancelExpiry([unpaid], client)).toBeNull();
  });

  test("msUntilNextClientCancelExpiry picks the soonest open window and skips closed ones", () => {
    const later = paidHearing({ hearing_id: "h2", payment_confirmed_at: new Date(PAID_MS + 20 * 60 * 1000).toISOString() });
    const expired = paidHearing({ hearing_id: "h3", payment_confirmed_at: new Date(PAID_MS - 2 * CLIENT_CANCEL_WINDOW_MS).toISOString() });
    const now = PAID_MS + 10 * 60 * 1000;
    expect(msUntilNextClientCancelExpiry([later, expired, paidHearing()], client, now)).toBe(50 * 60 * 1000);
    expect(msUntilNextClientCancelExpiry([expired], client, now)).toBeNull();
    expect(msUntilNextClientCancelExpiry(null, client, now)).toBeNull();
  });
});

describe("Share Case Details availability (B6)", () => {
  test("H/J: cancelled or otherwise closed paid hearing — form not offered", () => {
    for (const status of ["cancelled", "rejected", "expired"]) {
      expect(getHearingPermissions(paidHearing({ status }), client).canShareCaseDetails).toBe(false);
    }
  });

  test("I: active paid hearing without a brief — form offered to the requester only", () => {
    for (const status of ["broadcast", "accepted", "documents_shared"]) {
      expect(getHearingPermissions(paidHearing({ status }), client).canShareCaseDetails).toBe(true);
      expect(getHearingPermissions(paidHearing({ status }), counsel).canShareCaseDetails).toBe(false);
    }
  });

  test("not offered before payment or once already shared", () => {
    expect(getHearingPermissions(paidHearing({ payment_confirmed_at: null }), client).canShareCaseDetails).toBe(false);
    expect(getHearingPermissions(paidHearing({ details_submitted: true }), client).canShareCaseDetails).toBe(false);
  });
});
