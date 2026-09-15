import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty, TableLoading,
} from "@/components/ui/table";
import { FileText, Download } from "lucide-react";

/* Real content for the Documents workspace — today this is a view over the
   existing /files/mine (order documents). Once hearing documents (Phase 5)
   and Matter (schema-only for now) exist, this is where they'd be merged
   into the same aggregated list — the page doesn't need to change shape,
   only the query it renders. */
export default function Documents() {
  const [files, setFiles] = useState(null);

  useEffect(() => {
    api.get("/files/mine").then((r) => setFiles(r.data || [])).catch(() => setFiles([]));
  }, []);

  const open = async (fileId) => {
    try {
      const { data } = await api.get(`/files/${fileId}/download`);
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch {
      toast.error("Could not open this document");
    }
  };

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader
        eyebrow="Documents"
        eyebrowIcon={FileText}
        title="Every document, one view"
        description="Files you've uploaded across your orders."
      />
      <div className="mt-6 rounded-xl border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="px-3 sm:px-4">File</TableHead>
              {/* Type dropped below sm: with File/Pages/Date/action already at
                  their natural minimum, this 5th column was consistently the
                  one pushing the table's minimum width past a phone screen —
                  the badge already showing next to the filename would be the
                  first thing worth cutting, and this is the one entirely
                  redundant with the filename's own extension. */}
              <TableHead className="hidden sm:table-cell px-3 sm:px-4">Type</TableHead>
              <TableHead className="px-3 sm:px-4">Pages</TableHead>
              <TableHead className="px-3 sm:px-4">Date</TableHead>
              <TableHead className="px-3 sm:px-4"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {files === null && <TableLoading colSpan={5} />}
            {files?.length === 0 && <TableEmpty colSpan={5}>No documents uploaded yet</TableEmpty>}
            {files?.map((f) => (
              <TableRow key={f.file_id}>
                <TableCell className="px-3 sm:px-4 font-semibold truncate max-w-[9rem] sm:max-w-xs">
                  {f.original_filename}
                  <Badge variant="outline" className="sm:hidden ml-1.5 text-2xs uppercase align-middle">{f.content_type?.split("/")[1] || "file"}</Badge>
                </TableCell>
                <TableCell className="hidden sm:table-cell px-3 sm:px-4"><Badge variant="outline" className="text-2xs uppercase">{f.content_type?.split("/")[1] || "file"}</Badge></TableCell>
                <TableCell className="px-3 sm:px-4">{f.page_count || "—"}</TableCell>
                <TableCell className="px-3 sm:px-4 text-muted-foreground">{new Date(f.created_at).toLocaleDateString()}</TableCell>
                <TableCell className="px-3 sm:px-4">
                  <button type="button" onClick={() => open(f.file_id)} className="text-accent hover:underline inline-flex items-center gap-1 text-xs font-bold">
                    <Download className="w-3.5 h-3.5" /> Open
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </PageContainer>
  );
}
