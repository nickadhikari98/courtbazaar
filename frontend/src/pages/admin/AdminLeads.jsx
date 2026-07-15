import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Search, FileText, Download, CheckCircle2, XCircle, MessageSquareWarning, StickyNote,
} from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import {
  adminListLeads, adminGetLead, adminChangeLeadStatus, adminAddLeadNote,
  adminGetLeadDocumentUrl, adminGetLeadStats,
} from "@/lib/leadsApi";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "submitted", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "more_info_requested", label: "More Info" },
];

const ROLE_LABELS = {
  proxy_counsel: "Proxy Counsel",
  counsel: "Counsel",
  vendor: "Vendor",
  partner: "Partner",
  agent: "Agent",
};

const STATUS_BADGE = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  more_info_requested: "bg-blue-100 text-blue-700",
};

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <div className="text-2xl font-display font-black tracking-tight">{value}</div>
      <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}

function LeadDetailDialog({ leadId, open, onOpenChange, onChanged }) {
  const [lead, setLead] = useState(null);
  const [remark, setRemark] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !leadId) return;
    adminGetLead(leadId).then(setLead).catch(() => toast.error("Could not load application"));
  }, [open, leadId]);

  const changeStatus = async (status) => {
    setBusy(true);
    try {
      await adminChangeLeadStatus(leadId, status, remark || undefined);
      toast.success(`Application marked ${status.replace("_", " ")}`);
      setRemark("");
      const fresh = await adminGetLead(leadId);
      setLead(fresh);
      onChanged?.();
    } catch {
      toast.error("Could not update status");
    } finally {
      setBusy(false);
    }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    setBusy(true);
    try {
      await adminAddLeadNote(leadId, note.trim());
      setNote("");
      const fresh = await adminGetLead(leadId);
      setLead(fresh);
    } catch {
      toast.error("Could not add note");
    } finally {
      setBusy(false);
    }
  };

  const openDocument = async (docId) => {
    try {
      const { url } = await adminGetLeadDocumentUrl(leadId, docId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      toast.error("Could not generate a download link");
    }
  };

  if (!lead) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>Loading…</DialogTitle></DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display text-xl flex items-center gap-2">
            {lead.full_name || "Unnamed applicant"}
            <Badge className={`${STATUS_BADGE[lead.status]} border-0 font-bold uppercase text-2xs`}>
              {lead.status.replace("_", " ")}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {ROLE_LABELS[lead.role_applied_for] || lead.role_applied_for} · {lead.email || "no email"} · {lead.phone || "no phone"}
            {lead.email_verified ? " · email verified" : " · email not verified"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1 text-sm border rounded-lg p-3 max-h-56 overflow-y-auto">
          {Object.entries(lead.form_data || {}).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="text-muted-foreground min-w-[40%] flex-shrink-0">{k.split("__").pop().replace(/_/g, " ")}</span>
              <span className="font-medium break-words">{Array.isArray(v) ? v.join(", ") : String(v ?? "—")}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
            Documents ({lead.documents?.length || 0})
          </div>
          <div className="space-y-1.5">
            {(lead.documents || []).map((d) => (
              <button
                key={d.doc_id}
                type="button"
                onClick={() => openDocument(d.doc_id)}
                className="w-full flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-slate-50 text-left"
              >
                <FileText className="w-4 h-4 text-accent flex-shrink-0" />
                <span className="truncate flex-1">{d.original_filename}</span>
                <Download className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              </button>
            ))}
            {!lead.documents?.length && <p className="text-sm text-muted-foreground">No documents uploaded.</p>}
          </div>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Status history</div>
          <div className="space-y-1 text-xs text-muted-foreground">
            {(lead.status_history || []).map((h) => (
              <div key={h.history_id}>
                {h.from_status} → <b className="text-foreground">{h.to_status}</b> by {h.changed_by === "system" ? "system" : "admin"}
                {h.note ? ` — "${h.note}"` : ""}
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Internal notes</div>
          <div className="space-y-1 text-xs mb-2">
            {(lead.admin_remarks || []).map((r, i) => (
              <div key={i} className="bg-secondary rounded px-2 py-1">{r.text}</div>
            ))}
            {!lead.admin_remarks?.length && <p className="text-muted-foreground">No notes yet.</p>}
          </div>
          <div className="flex gap-2">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note (not sent to applicant)" />
            <Button type="button" variant="outline" onClick={addNote} disabled={busy}>
              <StickyNote className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="border-t pt-3">
          <Textarea
            value={remark}
            onChange={(e) => setRemark(e.target.value)}
            placeholder="Optional message to include in the applicant's email"
            rows={2}
            className="mb-2"
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy} onClick={() => changeStatus("approved")} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
              <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve
            </Button>
            <Button type="button" disabled={busy} onClick={() => changeStatus("more_info_requested")} variant="outline" className="font-bold">
              <MessageSquareWarning className="w-4 h-4 mr-1.5" /> Request More Info
            </Button>
            <Button type="button" disabled={busy} onClick={() => changeStatus("rejected")} variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50">
              <XCircle className="w-4 h-4 mr-1.5" /> Reject
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminLeads() {
  const [leads, setLeads] = useState([]);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [stats, setStats] = useState(null);
  const [activeLeadId, setActiveLeadId] = useState(null);

  const load = () => {
    adminListLeads({ status: status || undefined, q: q || undefined }).then(setLeads);
  };
  const loadStats = () => adminGetLeadStats().then(setStats).catch(() => {});

  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const totalSubmitted = useMemo(() => stats?.by_status
    ? Object.entries(stats.by_status).filter(([k]) => k !== "draft").reduce((a, [, v]) => a + v, 0)
    : 0, [stats]);

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Leads</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Lead management</h1>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <StatCard label="Total Applications" value={totalSubmitted} />
          <StatCard label="Pending Review" value={stats.by_status.submitted} />
          <StatCard label="Approved" value={stats.by_status.approved} />
          <StatCard label="Rejected" value={stats.by_status.rejected} />
          <StatCard label="Drafts" value={stats.by_status.draft} />
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <Tabs value={status} onValueChange={setStatus} className="flex-1">
          <TabsList className="flex-wrap h-auto">
            {STATUS_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, phone" className="pl-8" />
        </div>
      </div>

      <div className="space-y-3">
        {leads.length === 0 && <div className="text-center text-muted-foreground py-10">No applications</div>}
        {leads.map((l) => (
          <Card
            key={l.lead_id}
            className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveLeadId(l.lead_id)}
          >
            <CardContent className="p-5 flex flex-wrap items-center gap-4 justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="font-display font-bold text-lg">{l.full_name || "Unnamed applicant"}</div>
                  <Badge variant="outline" className="text-2xs font-bold uppercase">{ROLE_LABELS[l.role_applied_for] || l.role_applied_for}</Badge>
                </div>
                <div className="text-sm text-muted-foreground font-semibold">{l.email || "—"} · {l.phone || "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">{l.document_ids?.length || 0} documents · updated {new Date(l.updated_at).toLocaleDateString()}</div>
              </div>
              <Badge className={`${STATUS_BADGE[l.status]} border-0 font-bold uppercase`}>{l.status.replace("_", " ")}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      <LeadDetailDialog
        leadId={activeLeadId}
        open={!!activeLeadId}
        onOpenChange={(v) => !v && setActiveLeadId(null)}
        onChanged={() => { load(); loadStats(); }}
      />
    </PageContainer>
  );
}
