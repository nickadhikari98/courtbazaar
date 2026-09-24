import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, formatINR, downloadFile } from "@/lib/api";
import { escrowStatusLabel, escrowStatusClasses, isRetryableRefund, orphanRefundLabel, orphanRefundClasses, isRetryableOrphanRefund } from "@/config/escrowStatus";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty } from "@/components/ui/table";
import { Download, AlertTriangle, CheckCircle2, XCircle, Clock, RotateCcw, Lock } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import Loading from "@/components/shared/Loading";

export default function AdminReconciliation() {
  const [data, setData] = useState(null);
  const [gateway, setGateway] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [retrying, setRetrying] = useState(null);

  const load = async () => {
    const params = {};
    if (gateway !== "all") params.gateway = gateway;
    if (statusFilter !== "all") params.status_filter = statusFilter;
    const { data } = await api.get("/admin/reconciliation", { params });
    setData(data);
  };
  useEffect(() => { load(); }, [gateway, statusFilter]);

  // Reuses PR #54's POST /admin/escrow-transactions/{escrow_id}/retry-refund
  // (escrow.retry_refund: atomic claim + Razorpay lookup, so a double click
  // or a refund that already went through never refunds twice).
  const retryRefund = async (m) => {
    if (!window.confirm(`Retry the refund for escrow ${m.escrow_id}${m.amount != null ? ` (${formatINR(m.amount)})` : ""}? CourtBazaar first checks Razorpay for an existing refund and only requests what is still owed.`)) return;
    setRetrying(m.escrow_id);
    try {
      const { data: result } = await api.post(`/admin/escrow-transactions/${m.escrow_id}/retry-refund`);
      const label = escrowStatusLabel(result.status);
      if (result.status === "refunded") toast.success(`Refund completed — ${label}`);
      else if (result.status === "refund_failed") toast.error(`Refund still failing: ${result.refund_last_error || label}`);
      else toast.message(label);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not retry the refund");
    } finally {
      setRetrying(null);
    }
  };

  // Orphaned-capture refund retry (Bug C): POST /admin/payments/{razorpay_order_id}/retry-orphan-refund
  // — atomic claim + Razorpay lookup first, so it never refunds twice.
  const retryOrphanRefund = async (m) => {
    if (!window.confirm(`Retry the refund for orphaned payment ${m.razorpay_order_id}${m.amount != null ? ` (${formatINR(m.amount)})` : ""}? CourtBazaar first checks Razorpay for an existing refund and only requests what is still owed.`)) return;
    setRetrying(m.razorpay_order_id);
    try {
      const { data: result } = await api.post(`/admin/payments/${m.razorpay_order_id}/retry-orphan-refund`);
      const label = orphanRefundLabel(result.orphan_refund_status);
      if (result.orphan_refund_status === "processed") toast.success(label);
      else if (result.orphan_refund_status === "failed") toast.error(`${label}${result.orphan_refund_error ? `: ${result.orphan_refund_error}` : ""}`);
      else toast.message(label);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not retry the orphan refund");
    } finally {
      setRetrying(null);
    }
  };

  const exportCSV = () => downloadFile("/admin/reconciliation/export", "courtbazaar-reconciliation.csv");

  if (!data) return <Loading />;

  const StatusBadge = ({ s }) => {
    const map = {
      paid: ["bg-emerald-100 text-emerald-700", CheckCircle2],
      pending: ["bg-amber-100 text-amber-700", Clock],
      failed: ["bg-rose-100 text-rose-700", XCircle],
      initiated: ["bg-blue-100 text-blue-700", Clock],
      complete: ["bg-emerald-100 text-emerald-700", CheckCircle2],
    };
    const [cls, Icon] = map[s] || ["bg-secondary text-foreground", Clock];
    return <Badge className={`${cls} border-0 font-bold uppercase text-2xs flex items-center gap-1`}><Icon className="w-3 h-3" /> {s}</Badge>;
  };

  return (
    <PageContainer>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <PageHeader eyebrow="Admin · Payments" title="Reconciliation report" description="Stripe ↔ Razorpay cross-check" />
        <Button onClick={exportCSV} variant="outline" className="font-bold" data-testid="export-csv-btn">
          <Download className="w-4 h-4 mr-1.5" /> Export CSV
        </Button>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="dashboard-card border-none" data-testid="totals-stripe">
          <CardContent className="p-5">
            <div className="cb-overline">Stripe</div>
            <div className="font-display font-black text-2xl mt-1">{formatINR(data.totals.stripe.paid_amount)}</div>
            <div className="text-xs font-semibold mt-1 flex gap-2">
              <span className="text-emerald-700">{data.totals.stripe.paid} paid</span>
              <span className="text-amber-700">{data.totals.stripe.pending} pending</span>
              <span className="text-rose-700">{data.totals.stripe.failed} failed</span>
            </div>
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="totals-razorpay">
          <CardContent className="p-5">
            <div className="cb-overline">Razorpay</div>
            <div className="font-display font-black text-2xl mt-1">{formatINR(data.totals.razorpay.paid_amount)}</div>
            <div className="text-xs font-semibold mt-1 flex gap-2">
              <span className="text-emerald-700">{data.totals.razorpay.paid} paid</span>
              <span className="text-amber-700">{data.totals.razorpay.pending} pending</span>
              <span className="text-rose-700">{data.totals.razorpay.failed} failed</span>
              {data.totals.razorpay.orphaned > 0 && (
                <span className="text-muted-foreground" data-testid="totals-razorpay-orphaned">
                  {data.totals.razorpay.orphaned} orphaned ({formatINR(data.totals.razorpay.orphaned_amount)}, not counted)
                </span>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-primary text-white border-none" data-testid="totals-grand">
          <CardContent className="p-5">
            <div className="cb-overline text-white/60">Combined paid</div>
            <div className="font-display font-black text-3xl text-accent mt-1 tracking-tighter">{formatINR(data.totals.grand_total_paid)}</div>
            <div className="text-xs font-semibold mt-1 text-white/70">{data.totals.transaction_count} transactions</div>
          </CardContent>
        </Card>
      </div>

      {/* Mismatches */}
      {data.mismatches.length > 0 && (
        <Card className="mb-6 bg-rose-50 border-rose-200" data-testid="mismatches-card">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-rose-700" />
              <div className="font-display font-bold text-lg text-rose-900">{data.mismatches.length} mismatch(es) detected</div>
            </div>
            <div className="space-y-1 text-xs">
              {[
                // Actionable escrow refund issues are always shown (they carry a
                // Retry button); other mismatches keep the existing top-10 cap.
                ...data.mismatches.filter((m) => m.escrow_id || m.orphaned),
                ...data.mismatches.filter((m) => !m.escrow_id && !m.orphaned).slice(0, 10),
              ].map((m, i) => (
                m.escrow_id ? (
                  <div key={i} className="rounded-md bg-white/70 border border-rose-100 p-2 flex flex-wrap items-center gap-2" data-testid={`escrow-mismatch-${m.escrow_id}`}>
                    <Badge className={`${escrowStatusClasses(m.escrow_status)} border-0 font-bold text-2xs`}>{escrowStatusLabel(m.escrow_status)}</Badge>
                    <span className="font-mono"><b>{m.order_id}</b> · {m.reason}</span>
                    {m.payee_hold_locked && (
                      <span className="w-full flex items-center gap-1 text-amber-800 font-semibold">
                        <Lock className="w-3 h-3 flex-shrink-0" />
                        {`Counsel's held balance${m.payee_amount != null ? ` (${formatINR(m.payee_amount)})` : ""} stays locked until this refund succeeds. It can never be paid out from this escrow.`}
                      </span>
                    )}
                    {isRetryableRefund(m.escrow_status) && (
                      <Button size="sm" variant="outline" className="ml-auto font-bold h-7" disabled={retrying === m.escrow_id}
                              onClick={() => retryRefund(m)} data-testid={`retry-refund-${m.escrow_id}`}>
                        <RotateCcw className="w-3 h-3 mr-1" /> {retrying === m.escrow_id ? "Retrying…" : "Retry refund"}
                      </Button>
                    )}
                  </div>
                ) : m.orphaned ? (
                  <div key={i} className="rounded-md bg-white/70 border border-rose-100 p-2 flex flex-wrap items-center gap-2" data-testid={`orphan-mismatch-${m.razorpay_order_id}`}>
                    <Badge className={`${orphanRefundClasses(m.orphan_refund_status)} border-0 font-bold text-2xs`}>{orphanRefundLabel(m.orphan_refund_status)}</Badge>
                    <span className="font-mono"><b>{m.order_id}</b> · {m.reason}</span>
                    {m.razorpay_order_id && isRetryableOrphanRefund(m.orphan_refund_status) && (
                      <Button size="sm" variant="outline" className="ml-auto font-bold h-7" disabled={retrying === m.razorpay_order_id}
                              onClick={() => retryOrphanRefund(m)} data-testid={`retry-orphan-refund-${m.razorpay_order_id}`}>
                        <RotateCcw className="w-3 h-3 mr-1" /> {retrying === m.razorpay_order_id ? "Retrying…" : "Retry orphan refund"}
                      </Button>
                    )}
                  </div>
                ) : (
                  <div key={i} className="font-mono"><b>{m.order_id}</b> · {m.reason}</div>
                )
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <Select value={gateway} onValueChange={setGateway}>
          <SelectTrigger className="w-40" data-testid="gateway-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All gateways</SelectItem>
            <SelectItem value="stripe">Stripe</SelectItem>
            <SelectItem value="razorpay">Razorpay</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40" data-testid="status-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="paid">Paid</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card className="dashboard-card border-none overflow-hidden">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Txn / Session</TableHead>
                <TableHead>Gateway</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Order Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((r, i) => (
                <TableRow key={r.session_id + i} className={r.mismatch ? 'bg-rose-50' : ''} data-testid={`recon-row-${i}`}>
                  <TableCell className="font-mono text-xs">{r.session_id?.slice(0, 24)}{r.session_id?.length > 24 && '…'}</TableCell>
                  <TableCell>
                    <Badge className={`${r.gateway === 'stripe' ? 'bg-blue-100 text-blue-700' : 'bg-accent/15 text-accent'} border-0 font-bold uppercase text-2xs`}>{r.gateway}{r.simulated && ' SIM'}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.order_id}</TableCell>
                  <TableCell className="font-bold">{formatINR(r.amount)}</TableCell>
                  <TableCell><StatusBadge s={r.payment_status} /></TableCell>
                  <TableCell className="text-xs">{r.order_payment_status || "—"} {r.mismatch && <span className="text-rose-700 font-bold">⚠ MISMATCH</span>}{r.orphaned && <span className="text-muted-foreground font-bold"> · ORPHANED</span>}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString('en-IN') : '—'}</TableCell>
                </TableRow>
              ))}
              {data.rows.length === 0 && <TableEmpty colSpan={7}>No transactions</TableEmpty>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
