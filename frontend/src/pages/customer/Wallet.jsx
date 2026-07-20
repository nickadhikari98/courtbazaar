import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Wallet as WalletIcon, Plus, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";

export default function Wallet() {
  const { user, refresh } = useAuth();
  const [txns, setTxns] = useState([]);
  const [amount, setAmount] = useState(500);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const { data } = await api.get("/wallet");
    setTxns(data.transactions || []);
  };
  useEffect(() => { load(); }, []);

  const topUp = async () => {
    setLoading(true);
    try {
      await api.post("/wallet/add", { amount, description: "Manual top-up" });
      toast.success(`${formatINR(amount)} added to wallet`);
      await refresh();
      await load();
    } catch { toast.error("Could not top-up"); }
    finally { setLoading(false); }
  };

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader eyebrow="Wallet" title="Manage your balance" className="mb-6" />

      <Card className="relative bg-primary text-white border-none mb-6 overflow-hidden" data-testid="wallet-balance-card">
        <div className="absolute inset-0 cb-grain opacity-30"></div>
        <CardContent className="relative p-8">
          <div className="cb-overline text-white/60">Current balance</div>
          <div className="font-display font-black text-5xl mt-2 tracking-tighter">{formatINR(user?.wallet_balance || 0)}</div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Input type="number" value={amount} onChange={(e) => setAmount(parseInt(e.target.value) || 0)} className="w-32 bg-white/10 border-white/20 text-white" data-testid="wallet-amount-input" />
            <Button onClick={topUp} disabled={loading || amount <= 0} className="bg-accent hover:bg-accent/90 font-bold" data-testid="wallet-topup-btn">
              <Plus className="w-4 h-4 mr-1.5" /> Add to Wallet
            </Button>
            <div className="text-xs text-white/60 font-semibold ml-auto">Sandbox top-up</div>
          </div>
        </CardContent>
      </Card>

      <h2 className="font-display font-bold text-xl mb-3">Transaction history</h2>
      <Card className="dashboard-card border-none">
        <CardContent className="p-0">
          {txns.length === 0 ? (
            <div className="p-10 text-center">
              <WalletIcon className="w-10 h-10 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
              <div className="font-display font-bold">No transactions yet</div>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {txns.map((t, i) => (
                <div key={i} className="p-4 flex items-center justify-between" data-testid={`wallet-txn-${i}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${t.type === 'credit' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                      {t.type === 'credit' ? <ArrowDownLeft className="w-4 h-4" /> : <ArrowUpRight className="w-4 h-4" />}
                    </div>
                    <div>
                      <div className="font-semibold text-sm">{t.description}</div>
                      <div className="text-xs text-muted-foreground">{new Date(t.created_at).toLocaleString('en-IN')}</div>
                    </div>
                  </div>
                  <div className={`font-display font-bold ${t.type === 'credit' ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {t.type === 'credit' ? '+' : '-'}{formatINR(t.amount)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
