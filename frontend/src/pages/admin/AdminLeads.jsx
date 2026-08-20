import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Search, FileText, Download, CheckCircle2, XCircle, MessageSquareWarning, StickyNote, Trash2, Mail, RotateCcw,
} from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import StatCard from "@/components/shared/StatCard";
import {
  adminListLeads, adminGetLead, adminChangeLeadStatus, adminAddLeadNote,
  adminGetLeadDocumentUrl, adminGetLeadStats, adminDeleteLead, adminResendWelcomeEmail, adminReactivateUser,
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

function DeleteLeadDialog({ lead, open, onOpenChange, onDeleted }) {
  const [busy, setBusy] = useState(false);
  // Best-effort client-side hint only — the backend is the source of truth
  // (it also catches a registered account matched by email that this lead
  // was never explicitly converted from; see leads.py's delete_lead).
  const willDeactivate = !!lead?.converted_user_id;

  const confirmDelete = async () => {
    if (!lead) return;
    setBusy(true);
    try {
      const { action } = await adminDeleteLead(lead.lead_id);
      toast.success(action === "deactivated" ? "User account deactivated" : "Lead request deleted");
      onOpenChange(false);
      onDeleted?.(lead.lead_id);
    } catch {
      toast.error(willDeactivate ? "Could not deactivate this user" : "Could not delete this lead request");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      busy={busy}
      title={willDeactivate ? "Deactivate this user?" : "Delete lead request?"}
      description={willDeactivate ? (
        <>
          Are you sure you want to deactivate{" "}
          <b className="text-foreground">{lead?.full_name || "this user"}</b>? They will immediately lose
          access to CourtBazaar. Historical records will be preserved.
        </>
      ) : (
        <>
          Are you sure you want to permanently delete{" "}
          <b className="text-foreground">{lead?.full_name || "this applicant"}</b>'s{" "}
          {ROLE_LABELS[lead?.role_applied_for] || lead?.role_applied_for || "lead"} request? This action cannot
          be undone — the application and any uploaded documents will be permanently removed.
        </>
      )}
      confirmLabel={willDeactivate ? "Deactivate User" : "Delete"}
      confirmIcon={Trash2}
      onConfirm={confirmDelete}
    />
  );
}

function BulkDeleteLeadsDialog({ leads, open, onOpenChange, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const count = leads.length;
  const deactivateHint = leads.filter((l) => l.converted_user_id).length;

  const confirmDelete = async () => {
    if (!count) return;
    setBusy(true);
    try {
      const results = await Promise.allSettled(leads.map((l) => adminDeleteLead(l.lead_id)));
      const outcomes = leads.map((l, i) => ({ lead: l, result: results[i] }));
      const succeeded = outcomes.filter((o) => o.result.status === "fulfilled");
      const succeededIds = succeeded.map((o) => o.lead.lead_id);
      const deactivatedCount = succeeded.filter((o) => o.result.value?.action === "deactivated").length;
      const deletedCount = succeeded.length - deactivatedCount;
      const failedCount = count - succeeded.length;

      if (succeededIds.length) onDeleted?.(succeededIds);

      const parts = [];
      if (deletedCount) parts.push(`${deletedCount} lead${deletedCount === 1 ? "" : "s"} deleted`);
      if (deactivatedCount) parts.push(`${deactivatedCount} user${deactivatedCount === 1 ? "" : "s"} deactivated`);
      if (parts.length) toast.success(parts.join(" · "));
      if (failedCount) toast.error(`${failedCount} could not be processed`);
      if (succeededIds.length > 0 || failedCount === 0) onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      busy={busy}
      title={`Confirm removal of ${count} item${count === 1 ? "" : "s"}?`}
      description={(
        <>
          {deactivateHint === 0 && (
            <>
              Are you sure you want to permanently delete these <b className="text-foreground">{count}</b> lead
              request{count === 1 ? "" : "s"}? This action cannot be undone — the applications and any uploaded
              documents will be permanently removed.
            </>
          )}
          {deactivateHint === count && deactivateHint > 0 && (
            <>
              Are you sure you want to deactivate these <b className="text-foreground">{count}</b> users? They
              will immediately lose access to CourtBazaar. Historical records will be preserved.
            </>
          )}
          {deactivateHint > 0 && deactivateHint < count && (
            <>
              This selection is mixed: <b className="text-foreground">{count - deactivateHint}</b> lead
              request{count - deactivateHint === 1 ? "" : "s"} will be permanently deleted, and{" "}
              <b className="text-foreground">{deactivateHint}</b> registered user
              {deactivateHint === 1 ? "" : "s"} will be deactivated (access revoked, history preserved).
            </>
          )}
        </>
      )}
      confirmLabel={`Continue ${count === 1 ? "" : `(${count})`}`}
      confirmIcon={Trash2}
      onConfirm={confirmDelete}
    />
  );
}

function LeadDetailDialog({ leadId, open, onOpenChange, onChanged, onDeleteRequest }) {
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

  const resendWelcomeEmail = async () => {
    setBusy(true);
    try {
      const { email } = await adminResendWelcomeEmail(leadId);
      toast.success(`Set-password email resent to ${email}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not resend the email");
    } finally {
      setBusy(false);
    }
  };

  const reactivateAndResend = async () => {
    setBusy(true);
    try {
      await adminReactivateUser(lead.converted_user_id);
      const { email } = await adminResendWelcomeEmail(leadId);
      toast.success(`Account reactivated and set-password email resent to ${email}`);
      const fresh = await adminGetLead(leadId);
      setLead(fresh);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not reactivate the account");
    } finally {
      setBusy(false);
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
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto cb-scroll">
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

        <div className="space-y-1 text-sm border rounded-lg p-3 max-h-56 overflow-y-auto cb-scroll">
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
            {lead.converted_user_id && !lead.linked_account_deactivated && (
              <Button
                type="button"
                disabled={busy}
                onClick={resendWelcomeEmail}
                variant="outline"
                className="font-bold ml-auto"
              >
                <Mail className="w-4 h-4 mr-1.5" /> Resend Set-Password Email
              </Button>
            )}
            {lead.converted_user_id && lead.linked_account_deactivated && (
              <Button
                type="button"
                disabled={busy}
                onClick={reactivateAndResend}
                variant="outline"
                className="font-bold ml-auto"
              >
                <RotateCcw className="w-4 h-4 mr-1.5" /> Reactivate & Resend Email
              </Button>
            )}
            <Button
              type="button"
              disabled={busy}
              onClick={() => onDeleteRequest(lead)}
              variant="destructive"
              className={`font-bold ${lead.converted_user_id ? "" : "ml-auto"}`}
            >
              <Trash2 className="w-4 h-4 mr-1.5" /> {lead.converted_user_id ? "Deactivate User" : "Delete"}
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
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const load = () => {
    adminListLeads({ status: status || undefined, q: q || undefined }).then(setLeads);
    setSelectedIds(new Set());
  };
  const loadStats = () => adminGetLeadStats().then(setStats).catch(() => {});

  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const handleDeleted = (leadId) => {
    setLeads((prev) => prev.filter((l) => l.lead_id !== leadId));
    setSelectedIds((prev) => { const next = new Set(prev); next.delete(leadId); return next; });
    loadStats();
  };

  const handleBulkDeleted = (leadIds) => {
    const idSet = new Set(leadIds);
    setLeads((prev) => prev.filter((l) => !idSet.has(l.lead_id)));
    setSelectedIds((prev) => { const next = new Set(prev); leadIds.forEach((id) => next.delete(id)); return next; });
    loadStats();
  };

  const toggleSelect = (leadId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId); else next.add(leadId);
      return next;
    });
  };

  const allVisibleSelected = leads.length > 0 && selectedIds.size === leads.length;
  const toggleSelectAll = () => {
    setSelectedIds(allVisibleSelected ? new Set() : new Set(leads.map((l) => l.lead_id)));
  };

  const selectedLeads = useMemo(
    () => leads.filter((l) => selectedIds.has(l.lead_id)),
    [leads, selectedIds]
  );

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

      {leads.length > 0 && (
        <div className="flex items-center justify-between mb-2 px-1">
          <label className="flex items-center gap-2 text-sm text-muted-foreground font-semibold cursor-pointer select-none">
            <Checkbox checked={allVisibleSelected} onCheckedChange={toggleSelectAll} />
            Select all
          </label>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold">{selectedIds.size} selected</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                Clear
              </Button>
              <Button type="button" variant="destructive" size="sm" className="font-bold" onClick={() => setBulkDeleteOpen(true)}>
                <Trash2 className="w-4 h-4 mr-1.5" /> Delete selected
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        {leads.length === 0 && <div className="text-center text-muted-foreground py-10">No applications</div>}
        {leads.map((l) => (
          <Card
            key={l.lead_id}
            className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveLeadId(l.lead_id)}
          >
            <CardContent className="p-5 flex flex-wrap items-center gap-4 justify-between">
              <div className="flex items-center gap-4">
                <Checkbox
                  checked={selectedIds.has(l.lead_id)}
                  onCheckedChange={() => toggleSelect(l.lead_id)}
                  onClick={(e) => e.stopPropagation()}
                  aria-label={`Select ${l.full_name || "lead"}`}
                />
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="font-display font-bold text-lg">{l.full_name || "Unnamed applicant"}</div>
                    <Badge variant="outline" className="text-2xs font-bold uppercase">{ROLE_LABELS[l.role_applied_for] || l.role_applied_for}</Badge>
                  </div>
                  <div className="text-sm text-muted-foreground font-semibold">{l.email || "—"} · {l.phone || "—"}</div>
                  <div className="text-xs text-muted-foreground mt-1">{l.document_ids?.length || 0} documents · updated {new Date(l.updated_at).toLocaleDateString()}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={`${STATUS_BADGE[l.status]} border-0 font-bold uppercase`}>{l.status.replace("_", " ")}</Badge>
                <button
                  type="button"
                  title={l.converted_user_id ? "Deactivate linked user account" : "Delete lead request"}
                  aria-label={l.converted_user_id ? "Deactivate linked user account" : "Delete lead request"}
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(l); }}
                  className="p-1.5 rounded-md text-red-600 hover:bg-red-50 flex-shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <LeadDetailDialog
        leadId={activeLeadId}
        open={!!activeLeadId}
        onOpenChange={(v) => !v && setActiveLeadId(null)}
        onChanged={() => { load(); loadStats(); }}
        onDeleteRequest={(lead) => { setActiveLeadId(null); setDeleteTarget(lead); }}
      />

      <DeleteLeadDialog
        lead={deleteTarget}
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        onDeleted={handleDeleted}
      />

      <BulkDeleteLeadsDialog
        leads={selectedLeads}
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        onDeleted={handleBulkDeleted}
      />
    </PageContainer>
  );
}
