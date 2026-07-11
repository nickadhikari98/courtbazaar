import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  TrendingUp, IndianRupee, Truck, Receipt, Zap, Store, ShieldCheck, Users,
  Package, Crown, AlertCircle, Activity, FileX, Database
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis } from "recharts";

const COLORS = ["#0F172A", "#D97706", "#10b981", "#3b82f6", "#a855f7", "#ec4899", "#06b6d4", "#f59e0b"];

export default function SuperAdminConsole() {
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/admin/command-center").then(r => setData(r.data)); }, []);
  if (!data) return <div className="p-10">Loading command center…</div>;

  const revenuePie = [
    { name: "Commission (20%)", value: data.revenue.platform_commission_20pct },
    { name: "Delivery (50%)", value: data.revenue.platform_delivery_share_50pct },
    { name: "Convenience Fee", value: data.revenue.platform_convenience_fee },
    { name: "Urgent Surcharge", value: data.revenue.platform_urgent_share_20pct },
  ].filter(x => x.value > 0);

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-3 mb-6">
        <div>
          <div className="cb-overline text-accent flex items-center gap-1.5"><Crown className="w-3 h-3" /> Super Admin · Command Center</div>
          <h1 className="font-display font-black text-4xl tracking-tighter mt-1">Platform overview</h1>
          <p className="text-muted-foreground font-medium mt-1">Centralised view of revenue, orders, vendors, users, compliance.</p>
        </div>
        <Badge className="bg-emerald-100 text-emerald-700 border-0 font-bold flex items-center gap-1.5"><Activity className="w-3 h-3 live-dot" /> LIVE</Badge>
      </div>

      {/* Revenue Hero */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="lg:col-span-2 bg-gradient-to-br from-primary to-slate-800 text-white border-none" data-testid="hero-revenue">
          <CardContent className="p-7">
            <div className="cb-overline text-white/60">Total platform revenue</div>
            <div className="font-display font-black text-5xl tracking-tighter mt-2 text-accent">{formatINR(data.revenue.platform_total)}</div>
            <div className="text-sm font-semibold text-white/80 mt-1">across {data.revenue.paid_orders} paid orders · vendor payout: {formatINR(data.revenue.vendor_payout_total)}</div>
            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div data-testid="rev-commission"><div className="cb-overline text-white/60 text-[10px]">Commission 20%</div><div className="font-bold text-lg">{formatINR(data.revenue.platform_commission_20pct)}</div></div>
              <div data-testid="rev-delivery"><div className="cb-overline text-white/60 text-[10px]">Delivery 50%</div><div className="font-bold text-lg">{formatINR(data.revenue.platform_delivery_share_50pct)}</div></div>
              <div data-testid="rev-convenience"><div className="cb-overline text-white/60 text-[10px]">Convenience</div><div className="font-bold text-lg">{formatINR(data.revenue.platform_convenience_fee)}</div></div>
              <div data-testid="rev-urgent"><div className="cb-overline text-white/60 text-[10px]">Urgent 20%</div><div className="font-bold text-lg">{formatINR(data.revenue.platform_urgent_share_20pct)}</div></div>
            </div>
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="hero-revenue-pie">
          <CardContent className="p-5">
            <div className="cb-overline">Revenue mix</div>
            {revenuePie.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={revenuePie} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={3}>
                    {revenuePie.map((_, i) => <Cell key={i} fill={COLORS[i]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatINR(v)} />
                </PieChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground py-10 text-center">No paid orders yet</div>}
            <div className="text-xs font-semibold space-y-0.5 mt-2">
              {revenuePie.map((r, i) => (
                <div key={r.name} className="flex justify-between"><span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded" style={{backgroundColor: COLORS[i]}}></span>{r.name}</span><span>{formatINR(r.value)}</span></div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Revenue model card */}
      <Card className="bg-accent/5 border-accent/30 mb-6" data-testid="revenue-model-card">
        <CardContent className="p-5">
          <div className="cb-overline text-accent mb-2">Active revenue-sharing model</div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm font-semibold">
            <div><div className="text-xs text-muted-foreground">Platform commission</div><div className="font-display font-black text-2xl">{data.revenue_model.platform_commission_pct}%</div></div>
            <div><div className="text-xs text-muted-foreground">Vendor share</div><div className="font-display font-black text-2xl text-emerald-600">{100 - data.revenue_model.platform_commission_pct}%</div></div>
            <div><div className="text-xs text-muted-foreground">Delivery split</div><div className="font-display font-black text-2xl">50:50</div></div>
            <div><div className="text-xs text-muted-foreground">Convenience fee</div><div className="font-display font-black text-2xl">{formatINR(data.revenue_model.convenience_fee_inr)}</div></div>
            <div><div className="text-xs text-muted-foreground">GST</div><div className="font-display font-black text-2xl">{data.revenue_model.gst_pct}%</div></div>
          </div>
        </CardContent>
      </Card>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
        {[
          { label: "Orders 7d", val: data.orders.last_7_days, sub: `${data.orders.last_7_days_paid} paid`, icon: Package, link: "/orders" },
          { label: "Total orders", val: data.orders.total, sub: "all time", icon: Package },
          { label: "Vendors", val: data.vendors.approved, sub: `${data.vendors.pending_kyc} pending`, icon: Store, link: "/admin/vendors" },
          { label: "Sponsored", val: data.vendors.sponsored, sub: "active", icon: Crown },
          { label: "GST vendors", val: data.vendors.with_gst, sub: `${data.vendors.without_gst} non-GST`, icon: Receipt },
          { label: "Users", val: data.users.total, sub: `${data.compliance.deleted_users} deleted`, icon: Users, link: "/admin/users" },
          { label: "Audit log", val: data.compliance.audit_entries, sub: "entries", icon: Activity, link: "/admin/audit-log" },
          { label: "Files purged", val: data.compliance.files_purged, sub: "DPDP", icon: FileX },
          { label: "Pending KYC", val: data.vendors.pending_kyc, sub: "review", icon: AlertCircle, link: "/admin/vendors" },
          { label: "Deletion req.", val: data.compliance.pending_deletions, sub: "DPDP", icon: ShieldCheck },
          { label: "GST collected", val: formatINR(data.revenue.gst_collected), sub: "to govt", icon: IndianRupee },
          { label: "Vendor payout", val: formatINR(data.revenue.vendor_payout_total), sub: "lifetime", icon: TrendingUp },
        ].map(s => (
          <Card key={s.label} className="dashboard-card border-none hover:shadow-md transition-all" data-testid={`kpi-${s.label.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')}`}>
            <CardContent className="p-4">
              <div className="w-8 h-8 rounded-lg bg-accent/10 text-accent flex items-center justify-center mb-2"><s.icon className="w-4 h-4" /></div>
              <div className="cb-overline text-[10px]">{s.label}</div>
              <div className="font-display font-black text-xl tracking-tight mt-1 truncate">{s.val}</div>
              <div className="text-[10px] text-muted-foreground font-bold uppercase tracking-wide">{s.sub}</div>
              {s.link && <Link to={s.link} className="text-[10px] font-bold text-accent hover:underline mt-1 inline-block">View →</Link>}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Vendors by category + Orders by status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="dashboard-card border-none" data-testid="vendors-by-category">
          <CardContent className="p-5">
            <div className="cb-overline mb-3">Vendors by category</div>
            {data.vendors.by_category.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.vendors.by_category} layout="vertical">
                  <XAxis type="number" hide /><YAxis dataKey="category" type="category" tick={{ fontSize: 11, fontWeight: 600 }} width={130} />
                  <Tooltip cursor={{ fill: '#f1f5f9' }} />
                  <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                    {data.vendors.by_category.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground py-8 text-center">No vendors</div>}
          </CardContent>
        </Card>
        <Card className="dashboard-card border-none" data-testid="orders-by-status">
          <CardContent className="p-5">
            <div className="cb-overline mb-3">Orders by status</div>
            {data.orders.by_status.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.orders.by_status}>
                  <XAxis dataKey="status" tick={{ fontSize: 9 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip cursor={{ fill: '#f1f5f9' }} />
                  <Bar dataKey="count" fill="#D97706" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground py-8 text-center">No orders</div>}
          </CardContent>
        </Card>
      </div>

      {/* Quick links */}
      <Card className="mt-6 dashboard-card border-none">
        <CardContent className="p-5">
          <div className="cb-overline mb-3">Operational control</div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {[
              ["/admin", "Analytics", Activity], ["/admin/vendors", "Vendors", Store], ["/admin/pricing", "Pricing", IndianRupee],
              ["/admin/users", "Users", Users], ["/admin/reconciliation", "Reconciliation", Receipt],
              ["/admin/whatsapp", "WhatsApp", Activity], ["/admin/leaderboard", "Leaderboard", Crown],
              ["/admin/audit-log", "Audit Log", ShieldCheck],
            ].map(([href, label, Icon]) => (
              <Link key={href} to={href} className="flex items-center gap-2 p-3 bg-secondary hover:bg-accent/10 rounded-lg transition-all" data-testid={`quicklink-${label.toLowerCase()}`}>
                <Icon className="w-4 h-4 text-accent" />
                <span className="text-sm font-bold">{label}</span>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
