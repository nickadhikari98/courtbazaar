import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, Users, Store, IndianRupee, ShoppingBag, AlertCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell, PieChart, Pie } from "recharts";

const COLORS = ["#0F172A", "#D97706", "#10b981", "#3b82f6", "#a855f7"];

export default function AdminDashboard() {
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/admin/analytics").then(r => setData(r.data)); }, []);

  if (!data) return <div className="p-10">Loading…</div>;

  const stats = [
    { label: "Revenue (paid)", value: formatINR(data.revenue), icon: IndianRupee, color: "bg-accent/10 text-accent" },
    { label: "Platform commission", value: formatINR(data.platform_commission), icon: TrendingUp, color: "bg-emerald-100 text-emerald-700" },
    { label: "Total orders", value: data.total_orders, icon: ShoppingBag, color: "bg-blue-100 text-blue-700" },
    { label: "Users", value: data.total_users, icon: Users, color: "bg-purple-100 text-purple-700" },
    { label: "Approved vendors", value: data.total_vendors, icon: Store, color: "bg-cyan-100 text-cyan-700" },
    { label: "Pending KYC", value: data.pending_kyc, icon: AlertCircle, color: "bg-amber-100 text-amber-700" },
  ];

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="cb-overline text-accent">Admin console</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1 mb-6">Platform analytics</h1>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        {stats.map(s => (
          <Card key={s.label} className="dashboard-card border-none" data-testid={`admin-stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <CardContent className="p-4">
              <div className={`w-9 h-9 rounded-lg ${s.color} flex items-center justify-center mb-2`}><s.icon className="w-4 h-4" /></div>
              <div className="cb-overline text-[10px]">{s.label}</div>
              <div className="font-display font-black text-xl tracking-tight mt-1 truncate">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="dashboard-card border-none">
          <CardContent className="p-6">
            <h3 className="font-display font-bold text-lg mb-4 tracking-tight">Top services by demand</h3>
            {data.top_services?.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={data.top_services} layout="vertical">
                  <XAxis type="number" hide />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fontWeight: 600 }} width={140} />
                  <Tooltip cursor={{ fill: '#f1f5f9' }} />
                  <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                    {data.top_services.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground py-10 text-center">No orders yet</div>}
          </CardContent>
        </Card>

        <Card className="dashboard-card border-none">
          <CardContent className="p-6">
            <h3 className="font-display font-bold text-lg mb-4 tracking-tight">Court demand distribution</h3>
            {data.court_demand?.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={data.court_demand} dataKey="count" nameKey="name" innerRadius={60} outerRadius={100} paddingAngle={2}>
                    {data.court_demand.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground py-10 text-center">No orders yet</div>}
            <div className="mt-3 space-y-1.5">
              {data.court_demand?.map((c, i) => (
                <div key={c.court_id} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS[i % COLORS.length] }}></div>
                    <span className="font-semibold truncate">{c.name}</span>
                  </div>
                  <span className="font-bold">{c.count}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
