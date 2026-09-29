import React from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { ExternalLink, Download, Loader2, AlertCircle } from "lucide-react";

// Renders a document inline (iframe for PDFs/other, <img> for images) instead
// of handing the viewer off to a new browser tab — the presigned url is
// fetched with inline=true so the backend already sets an inline
// Content-Disposition; the browser's native PDF/image viewer then just runs
// inside this dialog.
//
// `loading`/`error` are optional — callers that resolve the url *before*
// opening the dialog (the original hearing-document callers) never pass
// them and get the original iframe-only behavior unchanged. `onDownload` is
// also optional; passing it adds an explicit "Download" action alongside
// "Open in new tab".
export default function DocumentPreviewDialog({
  open, onOpenChange, url, filename, contentType, loading = false, error = null, onDownload,
}) {
  const isImage = (contentType || "").toLowerCase().startsWith("image/");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl w-[95vw] h-[85vh] flex flex-col p-4">
        <DialogHeader>
          <DialogTitle className="font-display text-base flex items-center justify-between gap-3 pr-6">
            <span className="truncate">{filename || "Document preview"}</span>
            <div className="flex items-center gap-3 flex-shrink-0">
              {url && (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-2xs font-semibold text-accent hover:underline"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Open in new tab
                </a>
              )}
              {onDownload && (
                <button
                  type="button"
                  onClick={onDownload}
                  className="flex items-center gap-1 text-2xs font-semibold text-accent hover:underline"
                >
                  <Download className="w-3.5 h-3.5" /> Download
                </button>
              )}
            </div>
          </DialogTitle>
          <DialogDescription className="sr-only">Document preview</DialogDescription>
        </DialogHeader>
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-muted-foreground rounded-md border bg-white">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="text-xs font-medium">Loading preview…</span>
          </div>
        )}
        {!loading && error && (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-muted-foreground rounded-md border bg-white">
            <AlertCircle className="w-6 h-6 text-destructive" />
            <span className="text-xs font-medium">{error}</span>
          </div>
        )}
        {!loading && !error && url && (
          isImage ? (
            <div className="flex-1 w-full overflow-auto rounded-md border bg-white flex items-center justify-center">
              <img src={url} alt={filename || "Document preview"} className="max-w-full h-auto" />
            </div>
          ) : (
            <iframe src={url} title={filename || "Document preview"} className="flex-1 w-full rounded-md border bg-white" />
          )
        )}
      </DialogContent>
    </Dialog>
  );
}
