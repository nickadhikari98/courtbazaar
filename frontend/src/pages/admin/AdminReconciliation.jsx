import React, { useEffect, useState } from "react";
import { api, formatINR, API_BASE } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Download, AlertTriangle, CheckCircle2, XCircle, Clock } from "lucide-react";

export default function AdminReconciliation() {
  const [data, setData] = useState(null);
  const [gateway, setGateway] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const load = async () => {
    const params = {};
    if (gateway !== "all") params.gateway = gateway;
    if (statusFilter !== "all") params.status_filter = statusFilter;
    const { data } = await api.get("/admin/reconciliation", { params });
    setData(data);
  };
  useEffect(() => { load(); }, [gateway, statusFilter]);

  const exportCSV = () => {
    const token = localStorage.getItem("cb_token");
    fetch(`${API_BASE}/admin/reconciliation/export`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob()).then(b => {
        const url = URL.createObjectURL(b);
        const a = document.createElement("a");
        a.href = url; a.download = "courtbazaar-reconciliation.csv"; a.click();
      });
  };

  if (!data) return <div className="p-10">Loading…</div>;

  const StatusBadge = ({ s }) => {
    const map = {
      paid: ["bg-emerald-100 text-emerald-700", CheckCircle2],
      pending: ["bg-amber-100 text-amber-700", Clock],
      failed: ["bg-rose-100 text-rose-700", XCircle],
      initiated: ["bg-blue-100 text-blue-700", Clock],
      complete: ["bg-emerald-100 text-emerald-700", CheckCircle2],
    };
    const [cls, Icon] = map[s] || ["bg-secondary text-foreground", Clock];
    return <Badge className={`${cls} border-0 font-bold uppercase text-[10px] flex items-center gap-1`}><Icon className="w-3 h-3" /> {s}</Badge>;
  };

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <div className="cb-overline text-accent">Admin · Payments</div>
          <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Reconciliation report</h1>
          <p className="text-muted-foreground font-medium mt-1">Stripe ↔ Razorpay cross-check</p>
        </div>
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
              {data.mismatches.slice(0, 10).map((m, i) => (
                <div key={i} className="font-mono"><b>{m.order_id}</b> · {m.reason}</div>
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs cb-overline">
                  <th className="px-4 py-3">Txn / Session</th>
                  <th className="px-4 py-3">Gateway</th>
                  <th className="px-4 py-3">Order</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Order Status</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.rows.map((r, i) => (
                  <tr key={r.session_id + i} className={`hover:bg-secondary/40 ${r.mismatch ? 'bg-rose-50' : ''}`} data-testid={`recon-row-${i}`}>
                    <td className="px-4 py-3 font-mono text-xs">{r.session_id?.slice(0, 24)}{r.session_id?.length > 24 && '…'}</td>
                    <td className="px-4 py-3">
                      <Badge className={`${r.gateway === 'stripe' ? 'bg-blue-100 text-blue-700' : 'bg-accent/15 text-accent'} border-0 font-bold uppercase text-[10px]`}>{r.gateway}{r.simulated && ' SIM'}</Badge>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{r.order_id}</td>
                    <td className="px-4 py-3 font-bold">{formatINR(r.amount)}</td>
                    <td className="px-4 py-3"><StatusBadge s={r.payment_status} /></td>
                    <td className="px-4 py-3 text-xs">{r.order_payment_status || "—"} {r.mismatch && <span className="text-rose-700 font-bold">⚠ MISMATCH</span>}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString('en-IN') : '—'}</td>
                  </tr>
                ))}
                {data.rows.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">No transactions</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
