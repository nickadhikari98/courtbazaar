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

test("a single-hash line or other syntax is left as plain text", () => {
  expect(parseBlocks("# not a heading")[0]).toMatchObject({ type: "p", lines: ["# not a heading"] });
});
