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
import { Search, Trash2, Send, Mail, Phone } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import StatCard from "@/components/shared/StatCard";
import {
  adminListSupportTickets, adminGetSupportTicket, adminChangeSupportTicketStatus,
  adminDeleteSupportTicket, adminGetSupportTicketStats,
} from "@/lib/supportTicketsApi";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const STATUS_BADGE = {
  open: "bg-amber-100 text-amber-700",
  in_progress: "bg-blue-100 text-blue-700",
  resolved: "bg-emerald-100 text-emerald-700",
  closed: "bg-slate-100 text-slate-700",
};

const CATEGORY_LABELS = {
  order: "Order Issue",
  payment: "Payment",
  account: "Account",
  technical: "Technical Issue",
  feature_request: "Feature Request / Change",
  other: "Other",
};

function TicketDetailDialog({ ticketId, open, onOpenChange, onChanged }) {
  const [ticket, setTicket] = useState(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !ticketId) return;
    adminGetSupportTicket(ticketId).then(setTicket).catch(() => toast.error("Could not load ticket"));
  }, [open, ticketId]);

  const changeStatus = async (status) => {
    setBusy(true);
    try {
      await adminChangeSupportTicketStatus(ticketId, status, reply.trim() || undefined);
      toast.success(`Ticket marked ${status.replace("_", " ")}${reply.trim() ? " and reply sent" : ""}`);
      setReply("");
      const fresh = await adminGetSupportTicket(ticketId);
      setTicket(fresh);
      onChanged?.();
    } catch {
      toast.error("Could not update ticket");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await adminDeleteSupportTicket(ticketId);
      toast.success("Ticket deleted");
      onChanged?.();
      onOpenChange(false);
    } catch {
      toast.error("Could not delete ticket");
    } finally {
      setBusy(false);
    }
  };

  if (!ticket) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>Loading…</DialogTitle></DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto cb-scroll">
        <DialogHeader>
          <DialogTitle className="font-display text-xl flex items-center gap-2">
            #{ticket.ticket_id}
            <Badge className={`${STATUS_BADGE[ticket.status]} border-0 font-bold uppercase text-2xs`}>
              {ticket.status.replace("_", " ")}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {CATEGORY_LABELS[ticket.category] || ticket.category} · Submitted {new Date(ticket.created_at).toLocaleString()}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1 text-sm border rounded-lg p-3">
          <div className="font-display font-bold">{ticket.name}</div>
          <div className="flex items-center gap-1.5 text-muted-foreground"><Mail className="w-3.5 h-3.5" /> {ticket.email}</div>
          {ticket.phone && <div className="flex items-center gap-1.5 text-muted-foreground"><Phone className="w-3.5 h-3.5" /> {ticket.phone}</div>}
          {ticket.order_id && <div className="text-muted-foreground">Order: <b className="text-foreground">{ticket.order_id}</b></div>}
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">{ticket.subject}</div>
          <p className="text-sm whitespace-pre-wrap">{ticket.message}</p>
        </div>

        {ticket.replies?.length > 0 && (
          <div>
            <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Replies sent</div>
            <div className="space-y-2">
              {ticket.replies.map((r, i) => (
                <div key={i} className="bg-secondary rounded px-3 py-2 text-sm">
                  <p className="whitespace-pre-wrap">{r.text}</p>
                  <p className="text-2xs text-muted-foreground mt-1">{r.admin_name || "Admin"} · {new Date(r.created_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="border-t pt-3">
          <Textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Reply to the submitter (emailed to them, optional)"
            rows={3}
            className="mb-2"
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy} onClick={() => changeStatus("in_progress")} variant="outline" className="font-bold">
              Mark In Progress
            </Button>
            <Button type="button" disabled={busy} onClick={() => changeStatus("resolved")} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
              <Send className="w-4 h-4 mr-1.5" /> Resolve{reply.trim() ? " & Reply" : ""}
            </Button>
            <Button type="button" disabled={busy} onClick={() => changeStatus("closed")} variant="outline" className="font-bold">
              Close
            </Button>
            <Button type="button" disabled={busy} onClick={remove} variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50 ml-auto">
              <Trash2 className="w-4 h-4 mr-1.5" /> Delete
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminSupportTickets() {
  const [tickets, setTickets] = useState([]);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [stats, setStats] = useState(null);
  const [activeTicketId, setActiveTicketId] = useState(null);

  const load = () => {
    adminListSupportTickets({ status: status || undefined, q: q || undefined }).then(setTickets);
  };
  const loadStats = () => adminGetSupportTicketStats().then(setStats).catch(() => {});

  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const refreshAll = () => { load(); loadStats(); };

  const totalCount = useMemo(() => stats?.by_status
    ? Object.values(stats.by_status).reduce((a, v) => a + v, 0)
    : 0, [stats]);

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Support Tickets</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Support ticket management</h1>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard label="Total Tickets" value={totalCount} />
          <StatCard label="Open" value={stats.by_status.open} />
          <StatCard label="In Progress" value={stats.by_status.in_progress} />
          <StatCard label="Resolved" value={stats.by_status.resolved} />
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
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, subject" className="pl-8" />
        </div>
      </div>

      <div className="space-y-3">
        {tickets.length === 0 && <div className="text-center text-muted-foreground py-10">No support tickets</div>}
        {tickets.map((t) => (
          <Card
            key={t.ticket_id}
            className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveTicketId(t.ticket_id)}
          >
            <CardContent className="p-5 flex flex-wrap items-center gap-4 justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="font-display font-bold text-lg">#{t.ticket_id}</div>
                  <Badge variant="outline" className="text-2xs font-bold uppercase">{CATEGORY_LABELS[t.category] || t.category}</Badge>
                </div>
                <div className="text-sm font-semibold">{t.subject}</div>
                <div className="text-sm text-muted-foreground">{t.name} · {t.email}</div>
                <div className="text-xs text-muted-foreground mt-1">Updated {new Date(t.updated_at).toLocaleDateString()}</div>
              </div>
              <Badge className={`${STATUS_BADGE[t.status]} border-0 font-bold uppercase`}>{t.status.replace("_", " ")}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      <TicketDetailDialog
        ticketId={activeTicketId}
        open={!!activeTicketId}
        onOpenChange={(v) => !v && setActiveTicketId(null)}
        onChanged={refreshAll}
      />
    </PageContainer>
  );
}
