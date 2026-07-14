import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Hash } from "lucide-react";
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from "@/components/ui/command";
import { legalDocsList } from "@/content/legal";

/* Ctrl+K (Cmd+K on Mac) command-palette style search: jump straight to any
   section of the current document, or to any other legal document. Reuses
   the existing Command/Dialog primitives already used for comboboxes
   elsewhere in this app — no new UI dependency. */
export default function LegalSearchPalette({ currentDoc }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const otherDocs = useMemo(
    () => legalDocsList.filter((d) => d.slug !== currentDoc?.slug),
    [currentDoc]
  );

  const goToSection = (id) => {
    setOpen(false);
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.history.replaceState(null, "", `#${id}`);
    });
  };

  const goToDoc = (slug) => {
    setOpen(false);
    navigate(`/legal/${slug}`);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="legal-search-trigger"
        aria-label="Search this document"
      >
        <span>Search this document…</span>
        <kbd className="legal-search-kbd">Ctrl K</kbd>
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search sections or other policies…" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          {currentDoc?.sections?.length > 0 && (
            <CommandGroup heading={`In "${currentDoc.title}"`}>
              {currentDoc.sections.map((s) => (
                <CommandItem key={s.id} value={s.title} onSelect={() => goToSection(s.id)}>
                  <Hash className="opacity-50" />
                  <span>{s.title}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          <CommandGroup heading="Other Policies">
            {otherDocs.map((doc) => (
              <CommandItem key={doc.slug} value={doc.title} onSelect={() => goToDoc(doc.slug)}>
                <FileText className="opacity-50" />
                <span>{doc.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
