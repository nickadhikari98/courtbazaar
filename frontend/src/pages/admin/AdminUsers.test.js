/* Admin → Users bulk selection toolbar. Real AdminUsers page + ConfirmDialog;
   only the API client, auth context and toasts are mocked. The backend's
   bulk-delete endpoint is the authority on who can be removed — these pin
   what the UI lets an admin select and how it reports the results. */
import React from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";

import AdminUsers from "@/pages/admin/AdminUsers";
import { api } from "@/lib/api";

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() } }));
jest.mock("@/lib/api", () => ({
  api: { get: jest.fn(), put: jest.fn(), post: jest.fn() },
  formatINR: (n) => `₹${n}`,
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "user_me", role: "admin" } }) }));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const USERS = [
  { user_id: "user_me", name: "Me Admin", email: "me@cb.in", role: "admin", subscription: "free" },
  { user_id: "user_admin2", name: "Other Admin", email: "admin2@cb.in", role: "admin", subscription: "free" },
  { user_id: "user_a", name: "Asha Client", email: "asha@cb.in", role: "client", subscription: "free" },
  { user_id: "user_b", name: "Bharat Counsel", email: "bharat@cb.in", role: "proxy_counsel", subscription: "free" },
  { user_id: "user_c", name: "Chitra Vendor", email: "chitra@cb.in", role: "vendor", subscription: "free" },
  { user_id: "user_gone", name: "Gone Counsel", email: "gone@cb.in", role: "proxy_counsel", subscription: "free", deleted: true },
];

let container;
let root;
beforeEach(() => {
  jest.clearAllMocks();
  api.get.mockResolvedValue({ data: USERS });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const byTestId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = (el) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
const isChecked = (id) => byTestId(id).getAttribute("aria-checked") === "true";
const dialog = () => document.querySelector('[role="dialog"]');
const dialogButton = (label) => [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(label));
const typeSearch = (value) => act(() => {
  const input = byTestId("admin-users-search");
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});

const renderPage = async () => {
  act(() => root.render(<AdminUsers />));
  await flush();
};

describe("selection", () => {
  test("no selection: Select all shown, count/Clear/Delete hidden", async () => {
    await renderPage();
    expect(byTestId("admin-users-select-all")).not.toBeNull();
    expect(byTestId("admin-users-selected-count")).toBeNull();
    expect(byTestId("admin-users-clear-selection")).toBeNull();
    expect(byTestId("admin-users-delete-selected")).toBeNull();
  });

  test("Select all selects every displayed non-admin user (including deactivated), never self/admins", async () => {
    await renderPage();
    click(byTestId("admin-users-select-all"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("4 selected");
    ["user_a", "user_b", "user_c", "user_gone"].forEach((id) => expect(isChecked(`admin-user-select-${id}`)).toBe(true));
    ["user_me", "user_admin2"].forEach((id) => {
      expect(isChecked(`admin-user-select-${id}`)).toBe(false);
      expect(byTestId(`admin-user-select-${id}`).disabled).toBe(true);
    });
    // Toggling again deselects all.
    click(byTestId("admin-users-select-all"));
    expect(byTestId("admin-users-selected-count")).toBeNull();
  });

  test("Select all only covers the currently displayed (searched) list", async () => {
    await renderPage();
    typeSearch("bharat");
    click(byTestId("admin-users-select-all"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
  });

  test("individual checkboxes update the selected count", async () => {
    await renderPage();
    click(byTestId("admin-user-select-user_a"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
    click(byTestId("admin-user-select-user_c"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("2 selected");
    click(byTestId("admin-user-select-user_a"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
    // Clicking a protected row does nothing.
    click(byTestId("admin-user-select-user_me"));
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
  });

  test("Clear deselects everyone", async () => {
    await renderPage();
    click(byTestId("admin-users-select-all"));
    click(byTestId("admin-users-clear-selection"));
    expect(byTestId("admin-users-selected-count")).toBeNull();
    ["user_a", "user_b", "user_c", "user_gone"].forEach((id) => expect(isChecked(`admin-user-select-${id}`)).toBe(false));
  });
});

describe("bulk delete", () => {
  const withoutIds = (ids) => USERS.filter((u) => !ids.includes(u.user_id));

  test("Delete selected opens the confirmation modal; Cancel calls nothing", async () => {
    await renderPage();
    click(byTestId("admin-user-select-user_a"));
    click(byTestId("admin-users-delete-selected"));
    expect(dialog().textContent).toContain("ARE YOU SURE?");
    expect(dialog().textContent).toContain("This will permanently delete the selected users and cannot be undone.");
    click(dialogButton("Cancel"));
    await flush();
    expect(api.post).not.toHaveBeenCalled();
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
  });

  test("confirm permanently deletes active + deactivated users, removes them from the list, clears selection", async () => {
    api.post.mockResolvedValue({ data: { deleted: ["user_a", "user_gone"], skipped: [] } });
    await renderPage();
    click(byTestId("admin-user-select-user_a"));
    click(byTestId("admin-user-select-user_gone"));
    click(byTestId("admin-users-delete-selected"));
    api.get.mockResolvedValue({ data: withoutIds(["user_a", "user_gone"]) });
    click(dialogButton("Delete selected"));
    await flush();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/admin/users/bulk-delete", { user_ids: ["user_a", "user_gone"] });
    expect(api.put).not.toHaveBeenCalled(); // not the deactivate endpoint
    expect(api.get).toHaveBeenCalledTimes(2); // initial load + refresh
    expect(toast.success).toHaveBeenCalledWith("2 users permanently deleted");
    expect(dialog()).toBeNull();
    expect(byTestId("admin-users-selected-count")).toBeNull();
    expect(byTestId("admin-user-user_a")).toBeNull();
    expect(byTestId("admin-user-user_gone")).toBeNull();
    expect(byTestId("admin-user-user_b")).not.toBeNull();
  });

  test("API failure: error toast, dialog stays open, list and selection unchanged", async () => {
    api.post.mockRejectedValue({ response: { data: { detail: "Server exploded" } } });
    await renderPage();
    click(byTestId("admin-user-select-user_a"));
    click(byTestId("admin-users-delete-selected"));
    click(dialogButton("Delete selected"));
    await flush();

    expect(toast.error).toHaveBeenCalledWith("Server exploded");
    expect(toast.success).not.toHaveBeenCalled();
    expect(dialog()).not.toBeNull();
    expect(api.get).toHaveBeenCalledTimes(1); // no refresh
    expect(byTestId("admin-user-user_a")).not.toBeNull();
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
  });

  test("backend skips some users: deleted ones removed, skipped ones stay listed and selected", async () => {
    api.post.mockResolvedValue({ data: {
      deleted: ["user_a"],
      skipped: [{ user_id: "user_b", reason: "Has money held in escrow or a wallet balance" }],
    } });
    await renderPage();
    click(byTestId("admin-user-select-user_a"));
    click(byTestId("admin-user-select-user_b"));
    click(byTestId("admin-users-delete-selected"));
    api.get.mockResolvedValue({ data: withoutIds(["user_a"]) });
    click(dialogButton("Delete selected"));
    await flush();

    expect(toast.success).toHaveBeenCalledWith("1 user permanently deleted");
    expect(toast.error).toHaveBeenCalledWith("1 user could not be deleted: Has money held in escrow or a wallet balance");
    expect(byTestId("admin-user-user_a")).toBeNull();
    expect(byTestId("admin-users-selected-count").textContent).toBe("1 selected");
    expect(isChecked("admin-user-select-user_b")).toBe(true);
  });

  test("everything skipped: dialog stays open, nothing removed", async () => {
    api.post.mockResolvedValue({ data: { deleted: [], skipped: [{ user_id: "user_b", reason: "Has money held in escrow or a wallet balance" }] } });
    await renderPage();
    click(byTestId("admin-user-select-user_b"));
    click(byTestId("admin-users-delete-selected"));
    click(dialogButton("Delete selected"));
    await flush();

    expect(toast.success).not.toHaveBeenCalled();
    expect(dialog()).not.toBeNull();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(byTestId("admin-user-user_b")).not.toBeNull();
  });
});
test("blocked deletion with different reasons lists each reason once", async () => {
  api.post.mockResolvedValue({ data: { deleted: [], skipped: [
    { user_id: "user_a", reason: "Has money held in escrow or a wallet balance" },
    { user_id: "user_b", reason: "Has money held in escrow or a wallet balance" },
    { user_id: "user_c", reason: "Admin accounts cannot be deleted" },
  ] } });
  await renderPage();
  ["user_a", "user_b", "user_c"].forEach((id) => click(byTestId(`admin-user-select-${id}`)));
  click(byTestId("admin-users-delete-selected"));
  click(dialogButton("Delete selected"));
  await flush();

  expect(toast.error).toHaveBeenCalledWith(
    "3 users could not be deleted: Has money held in escrow or a wallet balance; Admin accounts cannot be deleted");
  expect(byTestId("admin-users-selected-count").textContent).toBe("3 selected");
});
