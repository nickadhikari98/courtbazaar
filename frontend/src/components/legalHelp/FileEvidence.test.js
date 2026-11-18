import React from "react";
import { createRoot } from "react-dom/client";
import AnswerCard, { normalizeAnswer } from "./AnswerCard";
import ChatSources, { documentCitationLinks, normalizeCitations } from "./ChatSources";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;

// A "Check it against the rules" card: one verified rule point, one point from the user's file.
const CITATIONS = [
  { title: "Arbitration and Conciliation Act, 1996", url: null, rules: ["7"], label: "Section", document: "Arbitration and Conciliation Act, 1996" },
  { title: "contract.docx, Clause 18 Arbitration", url: null, rules: [], document: "contract.docx", kind: "upload" },
];
const ANSWER = {
  status: "answered", summary: "An arbitration agreement shall be in writing (Section 7).",
  points: [
    { icon: "rule", tone: "neutral", title: "Section 7", badge: null, text: "It shall be in writing.", cite: [1] },
    { icon: "info", tone: "neutral", title: "Clause 18", badge: null, text: "Disputes go to arbitration in Mumbai.", cite: [2], source: "file" },
  ],
  note: "Points marked as from your file come from your own document, which is not a verified CourtBazaar source.",
};

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
const $$ = (id) => [...container.querySelectorAll(`[data-testid="${id}"]`)];

test("file points and file sources are marked as the user's own, unverified document", () => {
  const answer = normalizeAnswer(ANSWER);
  expect(answer.points.map((p) => p.source)).toEqual([null, "file"]);
  expect(normalizeAnswer({ ...ANSWER, points: [{ ...ANSWER.points[0], source: "web" }] }).points[0].source).toBeNull();
  // The file citation is kept, so the card's [2] still points at it.
  expect(normalizeCitations(CITATIONS).map((c) => [c.title, c.upload])).toEqual([
    ["Arbitration and Conciliation Act, 1996", false], ["contract.docx, Clause 18 Arbitration", true]]);

  act(() => root.render(
    <>
      <AnswerCard answer={answer} citeLinks={documentCitationLinks(CITATIONS)} clean={(t) => t} />
      <ChatSources citations={CITATIONS} />
    </>,
  ));
  expect($$("instant-legal-help-point-source").map((el) => el.textContent)).toEqual(["From your file"]);
  expect($$("instant-legal-help-source-upload").map((el) => el.textContent)).toEqual(["Your uploaded file · not a verified source"]);
  expect($$("instant-legal-help-answer-note")[0].textContent).toMatch(/not a verified CourtBazaar source/);
});
