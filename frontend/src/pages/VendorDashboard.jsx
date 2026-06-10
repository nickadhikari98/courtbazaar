import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Store, Package, TrendingUp, ShieldCheck, ArrowRight, Star, AlertCircle, Crown, Rocket, Trophy, Clock } from "lucide-react";

export default function VendorDashboard() {
  const { user } = useAuth();
  const [vendor, setVendor] = useState(null);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sponsorPlan, setSponsorPlan] = useState(null);
  const [sla, setSla] = useState(null);

  const loadAll = () => Promise.all([
    api.get("/vendors/me"),
    api.get("/orders"),
    api.get("/vendors/sponsored/plan"),
    api.get("/vendors/me/sla").catch(() => ({ data: null })),
  ]).then(([v, o, sp, s]) => {
    setVendor(v.data); setOrders(o.data || []); setSponsorPlan(sp.data); setSla(s.data); setLoading(false);
  });
  useEffect(() => { loadAll(); }, []);

  const activateSponsored = async () => {
    try {
      await api.post("/vendors/sponsored/activate");
      toast.success("Sponsored listing activated for 30 days!");
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  if (loading) return <div className="p-10">Loading…</div>;

  if (!vendor?.onboarded) {
    return (
      <div className="p-10 max-w-3xl mx-auto text-center">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
          <Store className="w-8 h-8 text-accent" />
        </div>
        <h1 className="font-display font-black text-3xl tracking-tighter">Complete vendor onboarding</h1>
        <p className="mt-2 text-muted-foreground font-medium">Set up your shop, courts and services to start receiving orders.</p>
        <Link to="/vendor/onboard">
          <Button className="mt-6 bg-accent font-bold" data-testid="start-onboard-btn">Start onboarding</Button>
        </Link>
      </div>
    );
  }

  const pending = orders.filter(o => ["placed", "matched"].includes(o.status));
  const active = orders.filter(o => ["accepted", "processing", "quality_check", "ready", "out_for_delivery"].includes(o.status));
  const completed = orders.filter(o => ["completed", "delivered"].includes(o.status));
  const earnings = orders.reduce((s, o) => s + (o.pricing?.vendor_payout || 0), 0);

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <div className="cb-overline text-accent">Vendor hub</div>
          <h1 className="font-display font-black text-3xl tracking-tighter mt-1 flex items-center gap-2">{vendor.shop_name}
            {vendor.kyc_status === 'approved' && <ShieldCheck className="w-6 h-6 text-emerald-600" />}
            {vendor.sponsored && <Badge className="bg-gradient-to-r from-accent to-amber-500 text-white border-0 font-bold uppercase text-[10px]"><Crown className="w-3 h-3 mr-1" /> Sponsored</Badge>}
          </h1>
          <div className="text-sm text-muted-foreground font-semibold flex items-center gap-2 mt-1">
            <Star className="w-3.5 h-3.5 text-accent fill-accent" /> {vendor.rating?.toFixed(1) || "—"} · {vendor.total_orders} orders · {vendor.court_ids?.length || 0} courts
          </div>
        </div>
        <Badge className={`${vendor.kyc_status === 'approved' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'} border-0 font-bold uppercase`} data-testid="kyc-badge">
          KYC: {vendor.kyc_status}
        </Badge>
      </div>

      {vendor.kyc_status === "pending" && (
        <Card className="mb-6 bg-amber-50 border-amber-200">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-700" />
            <div className="text-sm font-semibold">Your KYC is pending review. You'll start receiving orders once approved.</div>
          </CardContent>
        </Card>
      )}

      {/* Sponsored listing card */}
      {vendor.kyc_status === "approved" && (
        vendor.sponsored ? (
          <Card className="mb-6 bg-gradient-to-r from-accent to-amber-500 text-white border-none" data-testid="sponsored-active-card">
            <CardContent className="p-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Crown className="w-8 h-8" />
                <div>
                  <div className="font-display font-bold text-lg">Sponsored Listing Active</div>
                  <div className="text-sm text-white/90 font-semibold">Priority in auto-matching · Highlighted in directory</div>
                </div>
              </div>
              <div className="text-right">
                <div className="cb-overline text-white/70">Active until</div>
                <div className="font-bold">{vendor.sponsored_until ? new Date(vendor.sponsored_until).toLocaleDateString('en-IN') : '—'}</div>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="mb-6 border-accent bg-accent/5" data-testid="sponsored-promo-card">
            <CardContent className="p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <Rocket className="w-8 h-8 text-accent shrink-0" />
                <div>
                  <div className="font-display font-bold text-lg">Boost your orders 3× — Sponsored Listing</div>
                  <div className="text-sm text-muted-foreground font-medium">{sponsorPlan?.benefits?.join(' · ')}</div>
                </div>
              </div>
              <Button onClick={activateSponsored} className="bg-accent hover:bg-accent/90 font-bold h-12 px-5" data-testid="activate-sponsored-btn">
                Activate {formatINR(sponsorPlan?.price || 999)} / month
              </Button>
            </CardContent>
          </Card>
        )
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card className="dashboard-card border-none" data-testid="vendor-stat-pending"><CardContent className="p-5"><div className="cb-overline">Pending</div><div className="font-display font-black text-3xl mt-1">{pending.length}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="vendor-stat-active"><CardContent className="p-5"><div className="cb-overline">In Production</div><div className="font-display font-black text-3xl mt-1">{active.length}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="vendor-stat-completed"><CardContent className="p-5"><div className="cb-overline">Completed</div><div className="font-display font-black text-3xl mt-1">{completed.length}</div></CardContent></Card>
        <Card className="dashboard-card border-none" data-testid="vendor-stat-earnings"><CardContent className="p-5"><div className="cb-overline">Earnings (gross)</div><div className="font-display font-black text-3xl mt-1 text-accent">{formatINR(earnings)}</div></CardContent></Card>
      </div>

      {/* SLA scorecard */}
      {sla && sla.total_orders > 0 && (
        <Card className="mb-6 dashboard-card border-none" data-testid="vendor-sla-card">
          <CardContent className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
              <div>
                <div className="cb-overline text-accent flex items-center gap-1.5"><Trophy className="w-3 h-3" /> SLA scorecard</div>
                <div className="font-display font-bold text-xl mt-1">Performance grade</div>
              </div>
              <div className="text-right">
                <div className="font-display font-black text-5xl tracking-tighter">{sla.sla_score}</div>
                <Badge className={`${sla.grade === 'A+' ? 'bg-emerald-600' : sla.grade === 'A' ? 'bg-emerald-500' : sla.grade === 'B' ? 'bg-accent' : sla.grade === 'C' ? 'bg-amber-500' : 'bg-rose-500'} text-white border-0 font-black text-base px-3 py-0.5`}>{sla.grade}</Badge>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "On-time rate", val: `${sla.on_time_rate}%`, icon: Clock, color: sla.on_time_rate >= 80 ? 'text-emerald-600' : 'text-accent' },
                { label: "Avg TAT", val: `${sla.avg_turnaround_hours}h`, icon: TrendingUp, color: 'text-foreground' },
                { label: "Avg rating", val: sla.avg_rating ? `${sla.avg_rating}/5` : '—', icon: Star, color: 'text-accent' },
                { label: "Dispute rate", val: `${sla.dispute_rate}%`, icon: AlertCircle, color: sla.dispute_rate < 5 ? 'text-emerald-600' : 'text-rose-600' },
              ].map(m => (
                <div key={m.label} className="bg-secondary rounded-lg p-3" data-testid={`sla-${m.label.toLowerCase().replace(/\s+/g, '-')}`}>
                  <div className="cb-overline text-[10px] flex items-center gap-1"><m.icon className="w-3 h-3" /> {m.label}</div>
                  <div className={`font-display font-black text-2xl mt-1 ${m.color}`}>{m.val}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <h2 className="font-display font-bold text-2xl tracking-tight mb-3">Order queue</h2>
      <div className="space-y-3">
        {pending.length === 0 && active.length === 0 && (
          <Card className="border-dashed border-2"><CardContent className="p-10 text-center"><Package className="w-10 h-10 mx-auto text-muted-foreground mb-3" /><div className="font-display font-bold">No active orders</div></CardContent></Card>
        )}
        {[...pending, ...active].map(o => (
          <Link to={`/orders/${o.order_id}`} key={o.order_id} data-testid={`vendor-order-${o.order_id}`}>
            <Card className="dashboard-card border-none hover:shadow-md transition-all">
              <CardContent className="p-5 flex items-center justify-between gap-4">
                <div>
                  <div className="font-mono text-xs font-bold text-muted-foreground mb-1">{o.order_id}</div>
                  <div className="font-display font-bold text-lg">{o.court_name}</div>
                  <div className="text-sm text-muted-foreground">{o.services?.length} services · {o.delivery_option}</div>
                  <Badge className="bg-accent/10 text-accent border-0 text-[10px] mt-2 uppercase font-bold">{o.status.replace(/_/g, ' ')}</Badge>
                </div>
                <div className="text-right">
                  <div className="font-display font-black text-xl text-accent">{formatINR(o.pricing?.vendor_payout || 0)}</div>
                  <div className="text-xs text-muted-foreground font-semibold">your payout</div>
                  <ArrowRight className="w-4 h-4 ml-auto mt-2" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
