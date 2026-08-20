import React from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { ExternalLink } from "lucide-react";

// Renders a hearing document inline (iframe) instead of handing the viewer
// off to a new browser tab — the presigned url is fetched with inline=true
// so the backend already sets an inline Content-Disposition; the browser's
// native PDF/image viewer then just runs inside this dialog.
export default function DocumentPreviewDialog({ open, onOpenChange, url, filename }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl w-[95vw] h-[85vh] flex flex-col p-4">
        <DialogHeader>
          <DialogTitle className="font-display text-base flex items-center justify-between gap-2 pr-6">
            <span className="truncate">{filename || "Document preview"}</span>
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-2xs font-semibold text-accent hover:underline flex-shrink-0"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Open in new tab
              </a>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">Document preview</DialogDescription>
        </DialogHeader>
        {url && (
          <iframe src={url} title={filename || "Document preview"} className="flex-1 w-full rounded-md border bg-white" />
        )}
      </DialogContent>
    </Dialog>
  );
}
