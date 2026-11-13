import { parseBlocks } from "./ChatMarkdown";

test("groups headings, paragraphs and lists into blocks", () => {
  const blocks = parseBlocks("Intro line\nsecond line\n\n## Heading\n- a\n- b\n\n### Sub\n1. one\n2. two\nAfter");
  expect(blocks.map((b) => b.type)).toEqual(["p", "heading", "ul", "heading", "ol", "p"]);
  expect(blocks[0].lines).toEqual(["Intro line", "second line"]);
  expect(blocks[1]).toMatchObject({ level: 2, text: "Heading" });
  expect(blocks[2].items).toEqual(["a", "b"]);
  expect(blocks[3]).toMatchObject({ level: 3, text: "Sub" });
  expect(blocks[4]).toMatchObject({ items: ["one", "two"], start: 1 });
});

test("bullet characters used by plain replies still form a list", () => {
  expect(parseBlocks("• first\n• second")).toEqual([{ type: "ul", start: 1, items: ["first", "second"] }]);
});

test("indented list lines become sub-items of the item above", () => {
  const [list] = parseBlocks("1. one\n  - a\n  - b\n2. two");
  expect(list).toMatchObject({ type: "ol", items: ["one", "two"], children: { 0: ["a", "b"] } });
});

test("an indented line with no list above stays a top-level list", () => {
  expect(parseBlocks("  - a\n  - b")).toEqual([{ type: "ul", start: 1, items: ["a", "b"] }]);
});

test("--- is a divider; a dash bullet is not", () => {
  expect(parseBlocks("x\n\n---\n\ny").map((b) => b.type)).toEqual(["p", "hr", "p"]);
  expect(parseBlocks("- item")[0].type).toBe("ul");
});

test("a single-hash line or other syntax is left as plain text", () => {
  expect(parseBlocks("# not a heading")[0]).toMatchObject({ type: "p", lines: ["# not a heading"] });
});
