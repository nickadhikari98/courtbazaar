import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty, TableLoading,
} from "@/components/ui/table";
import { Wallet, IndianRupee, TrendingUp, Clock, Receipt, FileText } from "lucide-react";
import { formatINR } from "@/lib/api";
import { getEarningsMe, withdrawEarnings, getEarningsSettlements, getWallet } from "@/lib/earningsApi";
import StatGrid from "@/components/shared/StatGrid";

const SETTLEMENT_BADGE = {
  queued: "bg-amber-100 text-amber-700",
  paid: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

function WalletTab() {
  const [summary, setSummary] = useState(null);
  const [txns, setTxns] = useState(null);

  useEffect(() => {
    getEarningsMe().then(setSummary);
    getWallet().then((w) => setTxns(w.transactions));
  }, []);

  const stats = summary ? [
    { label: "Available Balance", value: formatINR(summary.available), icon: Wallet, color: "bg-accent/10 text-accent" },
    { label: "Pending", value: formatINR(summary.pending), icon: Clock, color: "bg-amber-100 text-amber-700" },
    { label: "Lifetime Earnings", value: formatINR(summary.lifetime), icon: TrendingUp, color: "bg-emerald-100 text-emerald-700" },
    { label: "This Month", value: formatINR(summary.monthly), icon: IndianRupee, color: "bg-blue-100 text-blue-700" },
  ] : [];

  return (
    <div className="space-y-6">
      <StatGrid stats={stats} />
      <div className="rounded-xl border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow><TableHead>Description</TableHead><TableHead>Type</TableHead><TableHead>Amount</TableHead><TableHead>Date</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {txns === null && <TableLoading colSpan={4} />}
            {txns?.length === 0 && <TableEmpty colSpan={4}>No transactions yet</TableEmpty>}
            {txns?.map((t, i) => (
              <TableRow key={i}>
                <TableCell>{t.description}</TableCell>
                <TableCell><Badge variant="outline" className={`text-2xs uppercase ${t.type === "credit" ? "text-emerald-700" : "text-red-600"}`}>{t.type}</Badge></TableCell>
                <TableCell className={t.type === "credit" ? "text-emerald-700 font-bold" : "text-red-600 font-bold"}>
                  {t.type === "credit" ? "+" : "-"}{formatINR(t.amount)}
                </TableCell>
                <TableCell className="text-muted-foreground">{new Date(t.created_at).toLocaleDateString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function WithdrawalsTab({ onWithdrawn }) {
  const [amount, setAmount] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [bankIfsc, setBankIfsc] = useState("");
  const [settlements, setSettlements] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () => getEarningsSettlements().then((s) => setSettlements(s.filter((x) => x.settlement_type === "withdrawal")));
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Enter a valid amount"); return; }
    setSubmitting(true);
    try {
      await withdrawEarnings(amt, bankAccount, bankIfsc);
      toast.success("Withdrawal requested — you'll be paid out via NEFT/UPI");
      setAmount(""); setBankAccount(""); setBankIfsc("");
      load();
      onWithdrawn?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not request withdrawal");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="dashboard-card border-none">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">Request a withdrawal</div>
          <form onSubmit={submit} className="grid sm:grid-cols-3 gap-3">
            <div>
              <Label>Amount</Label>
              <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="₹" />
            </div>
            <div>
              <Label>Bank account (optional)</Label>
              <Input value={bankAccount} onChange={(e) => setBankAccount(e.target.value)} />
            </div>
            <div>
              <Label>IFSC (optional)</Label>
              <Input value={bankIfsc} onChange={(e) => setBankIfsc(e.target.value)} />
            </div>
            <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold sm:col-span-3">
              Request Withdrawal
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="rounded-xl border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow><TableHead>Settlement</TableHead><TableHead>Amount</TableHead><TableHead>Status</TableHead><TableHead>Requested</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {settlements === null && <TableLoading colSpan={4} />}
            {settlements?.length === 0 && <TableEmpty colSpan={4}>No withdrawals yet</TableEmpty>}
            {settlements?.map((s) => (
              <TableRow key={s.settlement_id}>
                <TableCell className="font-mono text-xs">{s.settlement_id}</TableCell>
                <TableCell className="font-bold">{formatINR(s.amount)}</TableCell>
                <TableCell><Badge className={`${SETTLEMENT_BADGE[s.status] || ""} border-0 font-bold uppercase text-2xs`}>{s.status}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{new Date(s.created_at).toLocaleDateString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function SettlementsTab() {
  const [settlements, setSettlements] = useState(null);
  useEffect(() => { getEarningsSettlements().then(setSettlements); }, []);

  return (
    <div className="rounded-xl border bg-white overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow><TableHead>Settlement</TableHead><TableHead>Type</TableHead><TableHead>Amount</TableHead><TableHead>Status</TableHead><TableHead>Date</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {settlements === null && <TableLoading colSpan={5} />}
          {settlements?.length === 0 && <TableEmpty colSpan={5}>No settlements yet</TableEmpty>}
          {settlements?.map((s) => (
            <TableRow key={s.settlement_id}>
              <TableCell className="font-mono text-xs">{s.settlement_id}</TableCell>
              <TableCell><Badge variant="outline" className="text-2xs uppercase">{(s.settlement_type || "").replace("_", " ")}</Badge></TableCell>
              <TableCell className="font-bold">{formatINR(s.amount)}</TableCell>
              <TableCell><Badge className={`${SETTLEMENT_BADGE[s.status] || ""} border-0 font-bold uppercase text-2xs`}>{s.status}</Badge></TableCell>
              <TableCell className="text-muted-foreground">{new Date(s.created_at).toLocaleDateString()}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function InvoicesTab() {
  return (
    <Card className="border-dashed border-2">
      <CardContent className="p-10 text-center">
        <Receipt className="w-10 h-10 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
        <div className="font-display font-bold">Tax invoices coming soon</div>
        <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
          GST/tax invoices for professional earnings — and TDS — will appear here once wired up.
        </p>
      </CardContent>
    </Card>
  );
}

export default function Earnings() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <PageContainer className="max-w-4xl">
      <PageHeader eyebrow="Earnings" eyebrowIcon={Wallet} title="One wallet, every payout" />
      <Tabs defaultValue="wallet" className="mt-6">
        <TabsList>
          <TabsTrigger value="wallet">Wallet</TabsTrigger>
          <TabsTrigger value="withdrawals">Withdrawals</TabsTrigger>
          <TabsTrigger value="settlements">Settlements</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
        </TabsList>
        <TabsContent value="wallet" className="mt-4"><WalletTab key={`wallet-${refreshKey}`} /></TabsContent>
        <TabsContent value="withdrawals" className="mt-4">
          <WithdrawalsTab onWithdrawn={() => setRefreshKey((k) => k + 1)} />
        </TabsContent>
        <TabsContent value="settlements" className="mt-4"><SettlementsTab /></TabsContent>
        <TabsContent value="invoices" className="mt-4"><InvoicesTab /></TabsContent>
      </Tabs>
    </PageContainer>
  );
}
