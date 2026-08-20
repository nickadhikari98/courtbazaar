import React, { useEffect, useState } from "react";
import { api, formatINR, downloadFile } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Download, Play, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";

const statusColor = { queued: "bg-amber-100 text-amber-700", paid: "bg-emerald-100 text-emerald-700", failed: "bg-rose-100 text-rose-700" };

export default function AdminSettlements() {
  const [data, setData] = useState({ summary: {}, settlements: [] });
  const [status, setStatus] = useState("all");
  const [running, setRunning] = useState(false);
  const [paidOpen, setPaidOpen] = useState(false);
  const [activeS, setActiveS] = useState(null);
  const [utr, setUtr] = useState("");

  const load = async () => {
    const params = status !== "all" ? { status_filter: status } : {};
    const { data } = await api.get("/admin/settlements", { params });
    setData(data);
  };
  useEffect(() => { load(); }, [status]);

  const runCycle = async (dry = false) => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/settlements/run", { dry_run: dry });
      toast.success(`${dry ? '[Dry] ' : ''}${data.settlements_created} settlement(s) · ${formatINR(data.total_amount)}`);
      if (!dry) load();
    } catch { toast.error("Run failed"); }
    finally { setRunning(false); }
  };

  const exportCSV = (format = "h2h") => {
    const s = status === "all" ? "all" : status;
    const filename = format === "h2h" ? "courtbazaar-neft-h2h.csv" : "courtbazaar-settlements.csv";
    downloadFile(`/admin/settlements/export?status_filter=${s}&format=${format}`, filename);
  };

  const markPaid = async () => {
    try {
      await api.post(`/admin/settlements/${activeS.settlement_id}/mark-paid`, { utr });
      toast.success("Marked paid");
      setPaidOpen(false); setUtr("");
      load();
    } catch { toast.error("Failed"); }
  };

  const markFailed = async (id) => {
    const reason = prompt("Failure reason?") || "Unknown";
    try { await api.post(`/admin/settlements/${id}/mark-failed`, { reason }); toast.success("Marked failed · orders released"); load(); } catch { toast.error("Failed"); }
  };

  return (
    <PageContainer>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <PageHeader eyebrow="Admin · Settlements" title="Vendor payouts (T+1)" description="Daily NEFT/UPI batches · auto-runs at 02:00 UTC · manual trigger available" />
        <div className="flex gap-2">
          <Button onClick={() => runCycle(true)} variant="outline" className="font-bold" data-testid="run-dry-btn">Dry run</Button>
          <Button onClick={() => runCycle(false)} disabled={running} className="bg-primary font-bold" data-testid="run-cycle-btn">
            {running ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Play className="w-4 h-4 mr-1.5" />}
            Run T+1 cycle
          </Button>
          <Button onClick={() => exportCSV("h2h")} variant="outline" className="font-bold" data-testid="export-neft-btn">
            <Download className="w-4 h-4 mr-1.5" /> NEFT H2H CSV
          </Button>
          <Button onClick={() => exportCSV("legacy")} variant="ghost" className="font-bold" data-testid="export-legacy-btn">
            <Download className="w-4 h-4 mr-1.5" /> Simple CSV
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <Card className="dashboard-card border-none" data-testid="settle-total"><CardContent className="p-4"><div className="cb-overline">Total</div><div className="font-display font-black text-2xl">{data.summary.total_count || 0}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="settle-amount"><CardContent className="p-4"><div className="cb-overline">Total amount</div><div className="font-display font-black text-2xl text-accent">{formatINR(data.summary.total_amount || 0)}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="settle-queued"><CardContent className="p-4"><div className="cb-overline">Queued</div><div className="font-display font-black text-2xl text-amber-600">{data.summary.queued || 0}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="settle-paid"><CardContent className="p-4"><div className="cb-overline">Paid</div><div className="font-display font-black text-2xl text-emerald-600">{data.summary.paid || 0}</div></CardContent></Card>
      </div>

      <Tabs value={status} onValueChange={setStatus} className="mb-4">
        <TabsList data-testid="settle-tabs">
          <TabsTrigger value="all" data-testid="tab-all">All</TabsTrigger>
          <TabsTrigger value="queued" data-testid="tab-queued">Queued</TabsTrigger>
          <TabsTrigger value="paid" data-testid="tab-paid">Paid</TabsTrigger>
          <TabsTrigger value="failed" data-testid="tab-failed">Failed</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card className="dashboard-card border-none overflow-hidden">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Settlement ID</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead>Cycle</TableHead>
                <TableHead className="text-right">Orders</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.settlements.map(s => (
                <TableRow key={s.settlement_id} data-testid={`settle-row-${s.settlement_id}`}>
                  <TableCell className="font-mono text-xs">{s.settlement_id}</TableCell>
                  <TableCell>
                    <div className="font-display font-bold text-sm">{s.shop_name}</div>
                    <div className="text-xs text-muted-foreground font-mono">{s.bank_account || "—"} · {s.bank_ifsc || ""}</div>
                  </TableCell>
                  <TableCell className="text-xs font-mono">{s.cycle_date}</TableCell>
                  <TableCell className="text-right font-bold">{s.order_count}</TableCell>
                  <TableCell className="text-right font-bold">{formatINR(s.amount)}</TableCell>
                  <TableCell><Badge variant="outline" className="font-bold uppercase text-2xs">{s.payment_mode}</Badge></TableCell>
                  <TableCell><Badge className={`${statusColor[s.status] || ''} border-0 font-bold uppercase text-2xs`}>{s.status}</Badge>{s.utr && <div className="text-2xs font-mono mt-0.5">UTR: {s.utr}</div>}</TableCell>
                  <TableCell>
                    {s.status === "queued" && (
                      <div className="flex gap-1">
                        <Button onClick={() => { setActiveS(s); setPaidOpen(true); }} size="sm" className="bg-emerald-600 hover:bg-emerald-700 font-bold h-7 text-xs" data-testid={`mark-paid-${s.settlement_id}`}>
                          <CheckCircle2 className="w-3 h-3 mr-1" /> Paid
                        </Button>
                        <Button onClick={() => markFailed(s.settlement_id)} size="sm" variant="outline" className="h-7 text-xs text-rose-600 border-rose-300 font-bold" data-testid={`mark-failed-${s.settlement_id}`}>
                          <XCircle className="w-3 h-3" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {data.settlements.length === 0 && (
                <TableEmpty colSpan={8}>No settlements yet — click "Run T+1 cycle" to generate</TableEmpty>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={paidOpen} onOpenChange={setPaidOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Mark settlement {activeS?.settlement_id} as paid</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Amount: <b className="text-accent">{formatINR(activeS?.amount)}</b> to {activeS?.shop_name}</p>
          <Input value={utr} onChange={(e) => setUtr(e.target.value)} placeholder="UTR / transaction reference" data-testid="utr-input" />
          <DialogFooter><Button onClick={markPaid} className="bg-emerald-600 font-bold" data-testid="confirm-paid-btn">Confirm paid</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
