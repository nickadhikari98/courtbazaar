jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
import { groupChats } from "./ChatSidebar";

test("groupChats buckets by local day and drops empty groups", () => {
  const now = new Date(2026, 10, 17, 10, 0);
  const at = (d, h = 9) => ({ conversation_id: `c${d}_${h}`, updated_at: new Date(2026, 10, d, h).toISOString() });
  const groups = groupChats([at(17), at(16, 23), at(16, 0), at(12), at(1)], now);
  expect(groups.map(([label, items]) => [label, items.map((c) => c.conversation_id)])).toEqual([
    ["Today", ["c17_9"]],
    ["Yesterday", ["c16_23", "c16_0"]],
    ["Previous 7 days", ["c12_9"]],
    ["Older", ["c1_9"]],
  ]);
  expect(groupChats([], now)).toEqual([]);
});
