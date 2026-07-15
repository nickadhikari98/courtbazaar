import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, API_BASE } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Download, Trash2, ShieldCheck, Database, AlertTriangle } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";

export default function MyData() {
  const { user } = useAuth();
  const [reason, setReason] = useState("");
  const [delOpen, setDelOpen] = useState(false);
  const [summary, setSummary] = useState(null);

  const previewData = async () => {
    try {
      const { data } = await api.get("/dpdp/my-data");
      setSummary({
        orders: data.orders?.length || 0,
        files: data.files?.length || 0,
        wallet_transactions: data.wallet_transactions?.length || 0,
        payment_transactions: data.payment_transactions?.length || 0,
        ai_messages: data.ai_messages?.length || 0,
        audit_log: data.audit_log?.length || 0,
      });
      toast.success("Preview loaded");
    } catch { toast.error("Preview failed"); }
  };

  const download = () => {
    const token = localStorage.getItem("cb_token");
    fetch(`${API_BASE}/dpdp/my-data/download`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob()).then(b => {
        const url = URL.createObjectURL(b);
        const a = document.createElement("a");
        a.href = url; a.download = `courtbazaar-my-data-${user.user_id}.json`; a.click();
        toast.success("Download started");
      });
  };

  const requestDeletion = async () => {
    try {
      const { data } = await api.post("/dpdp/request-deletion", { reason });
      toast.success(data.message);
      setDelOpen(false);
      setReason("");
    } catch { toast.error("Could not submit request"); }
  };

  return (
    <PageContainer className="max-w-3xl">
      <PageHeader
        eyebrow="DPDP Act compliance"
        title="My data & privacy"
        description="Exercise your rights under India's Digital Personal Data Protection Act, 2023."
      />

      <Card className="mt-6 bg-emerald-50 border-emerald-200">
        <CardContent className="p-4 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-700" />
          <div className="text-sm font-bold text-emerald-900">CourtBazaar is DPDP Act compliant. Your data is encrypted in transit and at rest.</div>
        </CardContent>
      </Card>

      <Card className="mt-4 dashboard-card border-none">
        <CardContent className="p-6">
          <div className="flex items-start gap-3 mb-4">
            <Database className="w-8 h-8 text-accent" />
            <div>
              <div className="font-display font-bold text-xl">Right to access</div>
              <p className="text-sm text-muted-foreground font-medium mt-1">Download a complete machine-readable JSON of everything we hold about you — profile, orders, files, payments, AI history, audit log.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={previewData} variant="outline" className="font-bold" data-testid="preview-data-btn">Preview</Button>
            <Button onClick={download} className="bg-primary font-bold" data-testid="download-data-btn">
              <Download className="w-4 h-4 mr-1.5" /> Download all
            </Button>
          </div>
          {summary && (
            <div className="mt-4 grid grid-cols-3 gap-2 text-xs" data-testid="data-summary">
              {Object.entries(summary).map(([k, v]) => (
                <div key={k} className="bg-secondary rounded-lg p-2.5">
                  <div className="cb-overline text-[9px]">{k.replace(/_/g, ' ')}</div>
                  <div className="font-display font-black text-lg">{v}</div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4 border-destructive/30">
        <CardContent className="p-6">
          <div className="flex items-start gap-3 mb-4">
            <AlertTriangle className="w-8 h-8 text-destructive" />
            <div>
              <div className="font-display font-bold text-xl">Right to erasure</div>
              <p className="text-sm text-muted-foreground font-medium mt-1">Request permanent anonymisation of your account. Order records may be retained for legal/financial compliance (5-year retention per CrPC + GST law), but PII is removed.</p>
            </div>
          </div>
          <Dialog open={delOpen} onOpenChange={setDelOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="border-destructive text-destructive font-bold" data-testid="request-deletion-btn">
                <Trash2 className="w-4 h-4 mr-1.5" /> Request account deletion
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Request account deletion</DialogTitle></DialogHeader>
              <p className="text-sm text-muted-foreground">As per DPDP Act, we will process your request within 30 days. Order records may be retained for legal compliance with PII removed.</p>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" data-testid="deletion-reason-input" />
              <DialogFooter>
                <Button onClick={requestDeletion} className="bg-destructive font-bold" data-testid="deletion-submit-btn">Submit request</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
