import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, getErrorMessage } from "@/lib/api";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty, TableLoading,
} from "@/components/ui/table";
import { FileText } from "lucide-react";
import DocumentPreviewDialog from "@/components/shared/DocumentPreviewDialog";

/* Real content for the Documents workspace — /files/mine merges both
   upload flows server-side (order attachments from db.files, hearing
   uploads from db.hearing_documents), tagging each row with `source` so
   preview/download can route to the matching endpoint. Once Matter
   (schema-only for now) exists, it folds into the same aggregated list. */
export default function Documents() {
  const [files, setFiles] = useState(null);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null); // { file, url, loading, error }

  const load = useCallback(() => {
    setError(null);
    setFiles(null);
    api.get("/files/mine")
      .then((r) => setFiles(r.data || []))
      .catch((err) => setError(getErrorMessage(err, "Could not load your documents")));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Hearing-uploaded documents live in a separate store (db.hearing_documents)
  // keyed by hearing_id, not db.files — they need the hearing-scoped download
  // route. `inline` picks the presigned URL's Content-Disposition: inline for
  // in-modal preview, attachment for an explicit download.
  const fetchFileUrl = (f, inline) =>
    f.source === "hearing"
      ? api.get(`/hearing-requests/${f.hearing_id}/documents/${f.file_id}/download-url`, { params: { inline } }).then((r) => r.data)
      : api.get(`/files/${f.file_id}/download`, { params: { inline } }).then((r) => r.data);

  const openPreview = async (f) => {
    setPreview({ file: f, url: null, loading: true, error: null });
    try {
      const data = await fetchFileUrl(f, true);
      setPreview({ file: f, url: data.url, loading: false, error: null });
    } catch (err) {
      setPreview({ file: f, url: null, loading: false, error: getErrorMessage(err, "Could not load this document") });
    }
  };

  const downloadPreview = async () => {
    if (!preview?.file) return;
    try {
      const data = await fetchFileUrl(preview.file, false);
      const a = document.createElement("a");
      a.href = data.url;
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch {
      toast.error("Could not download this document");
    }
  };

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader
        eyebrow="Documents"
        eyebrowIcon={FileText}
        title="Every document, one view"
        description="Files you've uploaded across your orders and hearings."
      />
      <div className="mt-6 rounded-xl border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Pages</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {files === null && !error && <TableLoading colSpan={5} />}
            {error && (
              <TableEmpty colSpan={5}>
                <div className="flex flex-col items-center gap-2">
                  <span>{error}</span>
                  <button type="button" onClick={load} className="text-accent hover:underline text-xs font-bold">
                    Try again
                  </button>
                </div>
              </TableEmpty>
            )}
            {!error && files?.length === 0 && <TableEmpty colSpan={5}>No documents uploaded yet</TableEmpty>}
            {!error && files?.map((f) => (
              <TableRow key={f.file_id}>
                <TableCell className="font-semibold truncate max-w-xs">{f.original_filename}</TableCell>
                <TableCell><Badge variant="outline" className="text-2xs uppercase">{f.content_type?.split("/")[1] || "file"}</Badge></TableCell>
                <TableCell>{f.page_count || "—"}</TableCell>
                <TableCell className="text-muted-foreground">{new Date(f.created_at).toLocaleDateString()}</TableCell>
                <TableCell>
                  <button type="button" onClick={() => openPreview(f)} className="text-accent hover:underline inline-flex items-center gap-1 text-xs font-bold">
                    Open
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <DocumentPreviewDialog
        open={!!preview}
        onOpenChange={(v) => { if (!v) setPreview(null); }}
        url={preview?.url}
        filename={preview?.file?.original_filename}
        contentType={preview?.file?.content_type}
        loading={preview?.loading}
        error={preview?.error}
        onDownload={downloadPreview}
      />
    </PageContainer>
  );
}
