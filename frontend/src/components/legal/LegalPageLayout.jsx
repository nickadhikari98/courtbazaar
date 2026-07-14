import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Search, Printer, Link2, Share2, Download, ChevronDown, ArrowRight,
  FileText, Calendar, RefreshCw, Clock, ListOrdered,
} from "lucide-react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";
import { getLegalDoc } from "@/content/legal";
import Breadcrumb from "./Breadcrumb";
import ComplianceBanner from "./ComplianceBanner";
import ReadingProgressBar from "./ReadingProgressBar";
import LegalSearchPalette from "./LegalSearchPalette";
import LegalContentBlocks from "./LegalContentBlocks";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

function formatDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
}

function countWords(text) {
  return text ? text.trim().split(/\s+/).filter(Boolean).length : 0;
}

// Estimated from the document's own real word count (average 200 wpm
// reading speed) — not an invented figure.
function estimateReadingMinutes(doc) {
  let words = 0;
  doc.sections.forEach((s) => {
    s.body.forEach((block) => {
      if (block.type === "list") words += block.items.reduce((sum, i) => sum + countWords(i), 0);
      else if (block.type === "definition") words += countWords(block.term) + countWords(block.text);
      else words += countWords(block.text);
    });
  });
  return Math.max(1, Math.ceil(words / 200));
}

function sectionMatches(section, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  if (section.title.toLowerCase().includes(q)) return true;
  return section.body.some((block) => {
    if (block.type === "list") return block.items.some((i) => i.toLowerCase().includes(q));
    if (block.type === "definition") return block.term.toLowerCase().includes(q) || block.text.toLowerCase().includes(q);
    return block.text?.toLowerCase().includes(q);
  });
}

export default function LegalPageLayout({ doc }) {
  const [query, setQuery] = useState("");
  const [mobileTocOpen, setMobileTocOpen] = useState(false);
  const [activeSection, setActiveSection] = useState(doc.sections[0]?.id);
  const sectionRefs = useRef({});
  const tocScrollRef = useRef(null);

  usePageSEO({
    title: doc.title,
    description: doc.summary,
    path: `/legal/${doc.slug}`,
  });
  useStructuredData(
    "legal-doc-breadcrumb",
    breadcrumbSchema([
      { label: "Legal Center", href: "/legal" },
      { label: doc.title },
    ])
  );

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-96px 0px -70% 0px", threshold: 0 }
    );
    doc.sections.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [doc.sections]);

  // Keeps the active TOC item comfortably visible as the reader scrolls
  // through a long document — scrolls only the TOC's own internal list
  // (never the sticky card itself, and never the page), roughly centering
  // the active item. Scoped to the nearest scrollable ancestor
  // (.legal-toc-scroll) so it can't affect outer page scroll.
  useEffect(() => {
    if (!activeSection) return;
    const container = tocScrollRef.current;
    const activeLink = container?.querySelector(`[data-toc-id="${activeSection}"]`);
    if (!container || !activeLink) return;
    const containerRect = container.getBoundingClientRect();
    const linkRect = activeLink.getBoundingClientRect();
    const alreadyVisible = linkRect.top >= containerRect.top && linkRect.bottom <= containerRect.bottom;
    if (alreadyVisible) return;
    const target =
      container.scrollTop +
      (linkRect.top - containerRect.top) -
      container.clientHeight / 2 +
      linkRect.height / 2;
    container.scrollTo({ top: target, behavior: "smooth" });
  }, [activeSection]);

  // Deep-link support: /legal/terms#payments scrolls straight to that
  // section on load. Runs once per document (slug change), after the
  // sections have rendered, so the target element actually exists.
  useEffect(() => {
    const hash = window.location.hash?.slice(1);
    if (!hash) return;
    const id = requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.slug]);

  const filteredSections = useMemo(
    () => doc.sections.filter((s) => sectionMatches(s, query)),
    [doc.sections, query]
  );

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    const first = filteredSections[0];
    if (first) document.getElementById(first.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    // Keeps the URL shareable (e.g. /legal/terms#payments) without adding a
    // new browser-history entry for every TOC click.
    window.history.replaceState(null, "", `#${id}`);
    setMobileTocOpen(false);
  };

  const handleShare = async () => {
    const shareData = { title: doc.title, text: doc.summary, url: window.location.href };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
      } catch {
        /* user cancelled — no-op */
      }
    } else {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Link copied to clipboard.");
    }
  };

  const handleCopyLink = async () => {
    await navigator.clipboard.writeText(window.location.href);
    toast.success("Link copied to clipboard.");
  };

  const relatedDocs = (doc.relatedSlugs || []).map((slug) => getLegalDoc(slug)).filter(Boolean);
  const readingMinutes = useMemo(() => estimateReadingMinutes(doc), [doc]);

  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav />
      <ReadingProgressBar />

      <div className="legal-container">
        <div className="pt-6">
          <Breadcrumb items={[{ label: "Legal Center", href: "/legal" }, { label: doc.title }]} />
        </div>

        <div className="mt-4">
          <ComplianceBanner />
        </div>

        {/* Hero */}
        <div className="mt-8 pb-8 border-b border-slate-200 grid lg:grid-cols-[1fr_300px] gap-8 lg:gap-10 items-start">
          <div>
            <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">{doc.title}</h1>
            {doc.summary && <p className="text-muted-foreground mt-3 text-base max-w-2xl">{doc.summary}</p>}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mt-4 text-xs font-semibold text-muted-foreground">
              <span>Version {doc.version}</span>
              {doc.effectiveDate && <span>Effective: {formatDate(doc.effectiveDate)}</span>}
              {doc.lastUpdated && <span>Last Updated: {formatDate(doc.lastUpdated)}</span>}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2 mt-5 print:hidden">
              <button type="button" onClick={handleShare} className="legal-action-btn">
                <Share2 className="w-3.5 h-3.5" /> Share
              </button>
              <button type="button" onClick={handleCopyLink} className="legal-action-btn">
                <Link2 className="w-3.5 h-3.5" /> Copy Link
              </button>
              <button type="button" onClick={() => window.print()} className="legal-action-btn">
                <Printer className="w-3.5 h-3.5" /> Print
              </button>
              <button type="button" disabled className="legal-action-btn legal-action-btn--disabled" aria-label="Download PDF — coming soon">
                <Download className="w-3.5 h-3.5" /> Download PDF <ComingSoonBadge variant="inline" label="Soon" />
              </button>
            </div>
          </div>

          {/* Document info panel — fills the hero's right side on desktop with
              real, derived data only (no invented figures). */}
          <aside className="hidden lg:block legal-hero-info-card print:hidden">
            <p className="legal-hero-info-heading">Document Info</p>
            <dl className="space-y-3">
              <div className="legal-hero-info-row">
                <dt><FileText className="w-3.5 h-3.5" /> Version</dt>
                <dd>{doc.version}</dd>
              </div>
              <div className="legal-hero-info-row">
                <dt><Calendar className="w-3.5 h-3.5" /> Effective Date</dt>
                <dd>{formatDate(doc.effectiveDate) || "—"}</dd>
              </div>
              <div className="legal-hero-info-row">
                <dt><RefreshCw className="w-3.5 h-3.5" /> Last Updated</dt>
                <dd>{formatDate(doc.lastUpdated) || "—"}</dd>
              </div>
              <div className="legal-hero-info-row">
                <dt><Clock className="w-3.5 h-3.5" /> Reading Time</dt>
                <dd>{readingMinutes} min read</dd>
              </div>
              <div className="legal-hero-info-row">
                <dt><ListOrdered className="w-3.5 h-3.5" /> Sections</dt>
                <dd>{doc.sections.length}</dd>
              </div>
            </dl>

            {relatedDocs.length > 0 && (
              <>
                <div className="legal-hero-info-divider" />
                <p className="legal-hero-info-subheading">Related Policies</p>
                <ul className="space-y-1.5">
                  {relatedDocs.slice(0, 3).map((rd) => (
                    <li key={rd.slug}>
                      <Link to={`/legal/${rd.slug}`} className="legal-hero-info-link">
                        {rd.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        </div>

        <div className="grid lg:grid-cols-[240px_1fr] gap-10 py-10 print:block">
          {/* Desktop sticky TOC */}
          <aside className="hidden lg:block print:hidden">
            <div className="sticky top-24">
              <LegalSearchPalette currentDoc={doc} />
              <div className="legal-toc-card mt-1">
                <p className="legal-toc-heading">On This Page</p>
                <nav aria-label="Table of contents" className="legal-toc-scroll" ref={tocScrollRef}>
                  <ul className="space-y-0.5">
                    {doc.sections.map((s) => (
                      <li key={s.id}>
                        <button
                          type="button"
                          data-toc-id={s.id}
                          onClick={() => scrollToSection(s.id)}
                          className={`legal-toc-link ${activeSection === s.id ? "legal-toc-link--active" : ""}`}
                        >
                          {s.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </nav>
              </div>
            </div>
          </aside>

          {/* Mobile TOC accordion */}
          <div className="lg:hidden print:hidden">
            <LegalSearchPalette currentDoc={doc} />
            <button
              type="button"
              onClick={() => setMobileTocOpen((v) => !v)}
              className="legal-mobile-toc-trigger"
              aria-expanded={mobileTocOpen}
            >
              <span>On This Page</span>
              <ChevronDown className={`w-4 h-4 transition-transform ${mobileTocOpen ? "rotate-180" : ""}`} />
            </button>
            <div className="grid transition-all duration-300 ease-in-out" style={{ gridTemplateRows: mobileTocOpen ? "1fr" : "0fr" }}>
              <div className="overflow-hidden">
                <ul className="space-y-0.5 pt-2 pb-2">
                  {doc.sections.map((s) => (
                    <li key={s.id}>
                      <button type="button" onClick={() => scrollToSection(s.id)} className="legal-toc-link">
                        {s.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Content */}
          <div>
            <form onSubmit={handleSearchSubmit} className="legal-search-box print:hidden" role="search">
              <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search this document (e.g. refund, payment, cookies)…"
                aria-label="Search this document"
              />
            </form>

            {query && filteredSections.length === 0 && (
              <p className="text-sm text-muted-foreground mt-4">No matching sections for "{query}".</p>
            )}

            <div className="mt-6 space-y-10">
              {doc.sections.map((s) => (
                <section
                  key={s.id}
                  id={s.id}
                  className={`legal-section scroll-mt-28 ${query && !sectionMatches(s, query) ? "opacity-40" : ""}`}
                >
                  <h2 className="legal-section-title">{s.title}</h2>
                  <div className="legal-section-divider" />
                  <LegalContentBlocks blocks={s.body} query={query} />
                </section>
              ))}
            </div>

            {relatedDocs.length > 0 && (
              <div className="mt-14 pt-8 border-t border-slate-200 print:hidden">
                <h3 className="font-display font-bold text-base mb-4">Related Policies</h3>
                <div className="flex flex-wrap gap-2.5">
                  {relatedDocs.map((rd) => (
                    <Link key={rd.slug} to={`/legal/${rd.slug}`} className="legal-related-chip">
                      {rd.title} <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="print:hidden">
        <LandingFooter />
      </div>
    </div>
  );
}
