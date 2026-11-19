import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Practice from "@/pages/workspace/Practice";
import { getPracticeProfile } from "@/lib/practiceApi";

// Same react-router v7 / CRA jest resolver workaround as PracticeRespond.test.js.
jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/practiceApi", () => ({
  getPracticeProfile: jest.fn(),
  updatePracticeProfile: jest.fn(),
  listAvailabilitySlots: jest.fn(() => new Promise(() => {})),
  addAvailabilitySlot: jest.fn(),
  removeAvailabilitySlot: jest.fn(),
  getPracticePerformance: jest.fn(() => new Promise(() => {})),
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { user_id: "user_a", capabilities: ["can_practice_proxy_counsel"] }, hasCapability: () => true }),
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const forbidden = () => Object.assign(new Error("403"), {
  response: { status: 403, data: { detail: "Not available for this account" } },
});

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test("a 403 on the profile shows the server's reason and a retry, not an endless skeleton", async () => {
  getPracticeProfile.mockRejectedValueOnce(forbidden()).mockReturnValueOnce(new Promise(() => {}));
  await act(async () => { root.render(<MemoryRouter><Practice /></MemoryRouter>); });

  const card = container.querySelector("[data-testid=practice-load-error]");
  expect(card).not.toBeNull();
  expect(card.textContent).toContain("Not available for this account");

  await act(async () => { card.querySelector("button").click(); });
  expect(getPracticeProfile).toHaveBeenCalledTimes(2);
  expect(container.querySelector("[data-testid=practice-load-error]")).toBeNull(); // back to loading on retry
});
