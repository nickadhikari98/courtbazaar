import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, formatINR, API_BASE } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Upload, Download, XCircle, FileSpreadsheet, Loader2, AlertTriangle } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function BulkImport() {
  const { user } = useAuth();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = () => {
    const token = localStorage.getItem("cb_token");
    fetch(`${API_BASE}/firms/bulk-import/template`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob()).then(b => {
        const url = URL.createObjectURL(b);
        const a = document.createElement("a");
        a.href = url; a.download = "courtbazaar-bulk-template.csv"; a.click();
      });
  };

  const upload = async () => {
    if (!file) { toast.error("Pick a CSV first"); return; }
    setUploading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/firms/bulk-import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`${data.success.length} order(s) created · ${data.errors.length} error(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Upload failed"); }
    finally { setUploading(false); }
  };

  return (
    <PageContainer className="max-w-5xl">
      <div className="cb-overline text-accent">Law firm · Bulk import</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Matter-wise CSV bulk orders</h1>
      <p className="text-muted-foreground font-medium mt-1">Place dozens of orders across matters in one upload. Each row = one matter = one order.</p>

      {!user?.firm_id && (
        <Card className="mt-6 bg-amber-50 border-amber-200">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-700" />
            <div className="text-sm font-semibold">Bulk import is available for law-firm accounts. <a href="/firm" className="text-accent underline">Create or join a firm</a> first.</div>
          </CardContent>
        </Card>
      )}

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="dashboard-card border-none">
          <CardContent className="p-6">
            <FileSpreadsheet className="w-10 h-10 text-accent mb-3" />
            <div className="font-display font-bold text-lg">1. Download template</div>
            <p className="text-sm text-muted-foreground font-medium mt-1">
              CSV columns: matter_name, service_ids (semicolon-sep), qty_each, court_id, delivery_option, urgent, delivery_address, notes
            </p>
            <Button onClick={downloadTemplate} variant="outline" className="mt-4 font-bold" data-testid="download-template-btn">
              <Download className="w-4 h-4 mr-1.5" /> Download CSV
            </Button>
          </CardContent>
        </Card>

        <Card className="dashboard-card border-none">
          <CardContent className="p-6">
            <Upload className="w-10 h-10 text-accent mb-3" />
            <div className="font-display font-bold text-lg">2. Upload your CSV</div>
            <label className="mt-3 block border-2 border-dashed border-border rounded-xl p-5 text-center cursor-pointer hover:border-accent" data-testid="bulk-dropzone">
              <input type="file" accept=".csv" className="hidden" onChange={(e) => setFile(e.target.files[0])} />
              <div className="text-sm font-bold">{file ? file.name : "Drop CSV or tap to select"}</div>
            </label>
            <Button onClick={upload} disabled={!file || uploading || !user?.firm_id} className="mt-4 bg-accent font-bold w-full" data-testid="bulk-upload-btn">
              {uploading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Import orders
            </Button>
          </CardContent>
        </Card>
      </div>

      {result && (
        <div className="mt-6 space-y-4" data-testid="bulk-result">
          <div className="grid grid-cols-3 gap-3">
            <Card className="dashboard-card border-none bg-emerald-50">
              <CardContent className="p-4">
                <div className="cb-overline text-emerald-800">Created</div>
                <div className="font-display font-black text-3xl text-emerald-700">{result.success.length}</div>
              </CardContent>
            </Card>
            <Card className="dashboard-card border-none bg-rose-50">
              <CardContent className="p-4">
                <div className="cb-overline text-rose-800">Errors</div>
                <div className="font-display font-black text-3xl text-rose-700">{result.errors.length}</div>
              </CardContent>
            </Card>
            <Card className="dashboard-card border-none bg-accent/10">
              <CardContent className="p-4">
                <div className="cb-overline text-accent">Total amount</div>
                <div className="font-display font-black text-3xl text-accent">{formatINR(result.total_amount)}</div>
              </CardContent>
            </Card>
          </div>

          {result.success.length > 0 && (
            <Card className="dashboard-card border-none">
              <CardContent className="p-0">
                <div className="p-4 border-b border-border font-display font-bold">Created orders</div>
                <table className="w-full text-sm">
                  <thead className="bg-secondary text-xs cb-overline">
                    <tr><th className="px-4 py-2 text-left">Row</th><th className="px-4 py-2 text-left">Order ID</th><th className="px-4 py-2 text-left">Matter</th><th className="px-4 py-2 text-right">Total</th></tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {result.success.map(s => (
                      <tr key={s.order_id} data-testid={`bulk-success-${s.order_id}`}>
                        <td className="px-4 py-2 font-mono text-xs">{s.row}</td>
                        <td className="px-4 py-2 font-mono text-xs"><a href={`/orders/${s.order_id}`} className="text-accent font-bold hover:underline">{s.order_id}</a></td>
                        <td className="px-4 py-2 font-semibold">{s.matter}</td>
                        <td className="px-4 py-2 text-right font-bold">{formatINR(s.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {result.errors.length > 0 && (
            <Card className="dashboard-card border-none">
              <CardContent className="p-0">
                <div className="p-4 border-b border-border font-display font-bold text-rose-700">Errors</div>
                <div className="divide-y divide-border">
                  {result.errors.map((e, i) => (
                    <div key={i} className="p-4 flex items-start gap-3" data-testid={`bulk-error-${i}`}>
                      <XCircle className="w-4 h-4 text-rose-600 mt-0.5" />
                      <div className="text-sm">
                        <div className="font-mono text-xs text-muted-foreground">Row {e.row}</div>
                        <div className="font-semibold">{e.matter || "(no matter)"}</div>
                        <div className="text-xs text-rose-700 font-bold">{e.error}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </PageContainer>
  );
}
