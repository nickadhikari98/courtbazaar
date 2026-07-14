// Shared helpers for legal document content files. Each document ships as
// its own file in this folder (one file per policy, so updating a single
// policy — e.g. handing a lawyer one file — never touches any other file).
//
// Content model: a document has `sections`, each section has a `body` made
// of small typed blocks (`p`, `list`, `definition`, `callout`). This lets the
// shared layout render "larger headings, numbered sections, highlighted
// definitions, callout/warning/info boxes" without a markdown parser.

export function slugifySection(title) {
  return String(title)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-+|-+$)/g, "");
}

// Placeholder body for a section whose real legal text hasn't been supplied
// yet. Deliberately NOT legal language of any kind — just a clearly-flagged
// pending notice, so nothing resembling an actual clause ships by accident.
export function pendingBody(sectionTitle) {
  return [
    {
      type: "callout",
      variant: "notice",
      text: `This section ("${sectionTitle}") is pending final legal text from CourtBazaar's legal and compliance team. It will be replaced with the approved wording before this document is considered final.`,
    },
  ];
}

// Builds a full document from a flat list of section titles, each getting a
// pending placeholder body. Once approved text is available, replace
// `sectionTitles` usage below with an explicit `sections` array (each entry
// `{ id, title, body }`, body built from `p` / `list` / `definition` /
// `callout` blocks) — the rest of the system needs no changes.
export function makeDoc({
  slug,
  title,
  summary,
  version = "1.0",
  effectiveDate,
  lastUpdated,
  sectionTitles = [],
  sections,
  relatedSlugs = [],
}) {
  return {
    slug,
    title,
    version,
    effectiveDate,
    lastUpdated,
    summary,
    relatedSlugs,
    sections:
      sections ||
      sectionTitles.map((t) => ({ id: slugifySection(t), title: t, body: pendingBody(t) })),
  };
}
