import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty } from "@/components/ui/table";
import { toast } from "sonner";
import { Wallet, CheckCircle2, Clock, XCircle, Banknote, Receipt } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";

const statusColor = {
  queued: "bg-amber-100 text-amber-700 border-amber-300",
  paid: "bg-emerald-100 text-emerald-700 border-emerald-300",
  failed: "bg-rose-100 text-rose-700 border-rose-300",
};

const statusIcon = {
  queued: Clock,
  paid: CheckCircle2,
  failed: XCircle,
};

export default function VendorSettlements() {
  const [data, setData] = useState({ settlements: [], paid_lifetime: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("all");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await api.get("/vendors/me/settlements");
        if (alive) setData(data);
      } catch {
        toast.error("Could not load settlements");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const filtered = data.settlements.filter(s => tab === "all" ? true : s.status === tab);
  const failedTotal = data.settlements.filter(s => s.status === "failed").reduce((a, b) => a + (b.amount || 0), 0);

  return (
    <PageContainer data-testid="vendor-settlements-page">
      <div className="mb-6">
        <PageHeader
          eyebrow="Vendor · Settlements"
          title="My payouts"
          description="T+1 NEFT/UPI settlements · processed daily at 02:00 UTC for the previous day's delivered+paid orders"
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card className="dashboard-card border-none" data-testid="stat-paid-lifetime">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center"><Wallet className="w-4 h-4" /></div>
              <div className="cb-overline">Paid lifetime</div>
            </div>
            <div className="font-display font-black text-2xl text-emerald-600">{formatINR(data.paid_lifetime)}</div>
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="stat-pending">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center"><Clock className="w-4 h-4" /></div>
              <div className="cb-overline">Pending payout</div>
            </div>
            <div className="font-display font-black text-2xl text-amber-600">{formatINR(data.pending)}</div>
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="stat-failed">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center"><XCircle className="w-4 h-4" /></div>
              <div className="cb-overline">Failed (released)</div>
            </div>
            <div className="font-display font-black text-2xl text-rose-600">{formatINR(failedTotal)}</div>
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="stat-cycles">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center"><Receipt className="w-4 h-4" /></div>
              <div className="cb-overline">Total cycles</div>
            </div>
            <div className="font-display font-black text-2xl">{data.settlements.length}</div>
          </CardContent>
        </Card>
      </div>

      <Card className="dashboard-card border-none mb-5 bg-gradient-to-br from-primary to-slate-800 text-white">
        <CardContent className="p-5 flex flex-wrap items-center gap-4 justify-between">
          <div>
            <div className="cb-overline text-white/60">How payouts work</div>
            <div className="font-display font-bold text-lg mt-1">80% vendor share · auto-settled T+1</div>
            <p className="text-sm text-white/70 mt-1 max-w-2xl">
              When an order is marked <b>delivered</b> and the customer payment is captured, we batch it into the next day&apos;s
              02:00 UTC settlement run. NEFT for accounts, UPI fallback otherwise. Failed transfers auto-release for re-batch.
            </p>
          </div>
          <Badge className="bg-accent text-white border-0 font-bold uppercase tracking-wider">T+1 Auto</Badge>
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList data-testid="vendor-settle-tabs">
          <TabsTrigger value="all" data-testid="vtab-all">All</TabsTrigger>
          <TabsTrigger value="queued" data-testid="vtab-queued">Queued</TabsTrigger>
          <TabsTrigger value="paid" data-testid="vtab-paid">Paid</TabsTrigger>
          <TabsTrigger value="failed" data-testid="vtab-failed">Failed</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card className="dashboard-card border-none overflow-hidden">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Settlement ID</TableHead>
                  <TableHead>Cycle date</TableHead>
                  <TableHead className="text-right">Orders</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>UTR / Status</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(s => {
                  const SI = statusIcon[s.status] || Clock;
                  return (
                    <TableRow key={s.settlement_id} data-testid={`vendor-settle-row-${s.settlement_id}`}>
                      <TableCell className="font-mono text-xs font-bold">{s.settlement_id}</TableCell>
                      <TableCell className="text-xs font-mono">{s.cycle_date}</TableCell>
                      <TableCell className="text-right font-bold">{s.order_count}</TableCell>
                      <TableCell className="text-right font-display font-black text-base">{formatINR(s.amount)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-bold uppercase text-2xs">
                          <Banknote className="w-3 h-3 mr-1" />{s.payment_mode}
                        </Badge>
                        <div className="text-2xs font-mono text-muted-foreground mt-0.5">{s.bank_account ? `••${s.bank_account.slice(-4)}` : "UPI"}</div>
                      </TableCell>
                      <TableCell className="text-xs font-mono">
                        {s.utr || s.failure_reason || "—"}
                      </TableCell>
                      <TableCell>
                        <Badge className={`${statusColor[s.status]} border font-bold uppercase text-2xs`}>
                          <SI className="w-3 h-3 mr-1" />{s.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filtered.length === 0 && (
                  <TableEmpty colSpan={7}>
                    <div className="font-display font-bold text-base mb-1">No settlements yet</div>
                    <div className="text-sm">Complete an order — your payout will appear in the next T+1 cycle.</div>
                  </TableEmpty>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
