import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Trophy, Crown, Star, TrendingUp, Clock, ShieldCheck, Award } from "lucide-react";

const gradeColors = {
  "A+": "bg-emerald-600 text-white",
  "A": "bg-emerald-500 text-white",
  "B": "bg-accent text-white",
  "C": "bg-amber-500 text-white",
  "D": "bg-rose-500 text-white",
};

export default function AdminLeaderboard() {
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/admin/leaderboard").then(r => { setVendors(r.data || []); setLoading(false); });
  }, []);

  const top3 = vendors.slice(0, 3);
  const rest = vendors.slice(3);

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="cb-overline text-accent">Admin · Performance</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Vendor leaderboard & SLA</h1>
      <p className="text-muted-foreground font-medium mt-1">Ranked by composite SLA score (on-time × 35% + completion × 25% + rating × 25% + dispute-free × 15%)</p>

      {loading ? <div className="mt-6">Loading…</div> : (
        <>
          {/* Top 3 podium */}
          {top3.length > 0 && (
            <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
              {top3.map((v, i) => {
                const podiumIcons = [Crown, Award, Trophy];
                const Icon = podiumIcons[i];
                const podiumBg = ["bg-gradient-to-br from-accent to-amber-500", "bg-gradient-to-br from-slate-500 to-slate-600", "bg-gradient-to-br from-orange-600 to-orange-700"];
                return (
                  <Card key={v.vendor_id} className={`text-white border-none ${podiumBg[i]}`} data-testid={`podium-${i+1}`}>
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between mb-3">
                        <Icon className="w-10 h-10" />
                        <div className="font-display font-black text-5xl tracking-tighter opacity-30">#{i+1}</div>
                      </div>
                      <div className="font-display font-bold text-xl truncate">{v.shop_name}</div>
                      <div className="text-xs text-white/80 font-semibold mt-0.5">{v.city || "—"}</div>
                      <div className="mt-4 flex items-end gap-2">
                        <span className="font-display font-black text-4xl tracking-tighter">{v.sla_score}</span>
                        <span className="text-xs font-bold opacity-80 mb-1.5">SLA</span>
                        <Badge className={`${gradeColors[v.grade]} border-0 font-black ml-auto`}>{v.grade}</Badge>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-semibold">
                        <div><div className="opacity-70">On-time</div><div className="text-base font-bold">{v.on_time_rate}%</div></div>
                        <div><div className="opacity-70">Avg TAT</div><div className="text-base font-bold">{v.avg_turnaround_hours}h</div></div>
                        <div><div className="opacity-70">Rating</div><div className="text-base font-bold">{v.avg_rating}/5</div></div>
                        <div><div className="opacity-70">Orders</div><div className="text-base font-bold">{v.total_orders}</div></div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          {/* Full table */}
          {rest.length > 0 && (
            <Card className="mt-6 dashboard-card border-none overflow-hidden">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary text-xs cb-overline text-left">
                      <tr><th className="px-4 py-3">Rank</th><th className="px-4 py-3">Vendor</th><th className="px-4 py-3">Grade</th><th className="px-4 py-3 text-right">SLA</th><th className="px-4 py-3 text-right">On-time</th><th className="px-4 py-3 text-right">Avg TAT</th><th className="px-4 py-3 text-right">Rating</th><th className="px-4 py-3 text-right">Orders</th><th className="px-4 py-3 text-right">Revenue</th><th className="px-4 py-3 text-right">Disputes</th></tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {rest.map((v, i) => (
                        <tr key={v.vendor_id} className="hover:bg-secondary/40" data-testid={`leaderboard-row-${i}`}>
                          <td className="px-4 py-3 font-mono font-bold">{i + 4}</td>
                          <td className="px-4 py-3">
                            <div className="font-display font-bold flex items-center gap-1.5">{v.shop_name}
                              {v.sponsored && <Crown className="w-3.5 h-3.5 text-accent fill-accent" />}
                            </div>
                            <div className="text-xs text-muted-foreground">{v.city} · {v.court_count} courts</div>
                          </td>
                          <td className="px-4 py-3"><Badge className={`${gradeColors[v.grade]} border-0 font-black`}>{v.grade}</Badge></td>
                          <td className="px-4 py-3 text-right font-bold">{v.sla_score}</td>
                          <td className="px-4 py-3 text-right">{v.on_time_rate}%</td>
                          <td className="px-4 py-3 text-right">{v.avg_turnaround_hours}h</td>
                          <td className="px-4 py-3 text-right">{v.avg_rating ? `${v.avg_rating}/5` : "—"}</td>
                          <td className="px-4 py-3 text-right font-semibold">{v.total_orders}</td>
                          <td className="px-4 py-3 text-right font-semibold">{formatINR(v.revenue)}</td>
                          <td className="px-4 py-3 text-right">{v.dispute_rate}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {vendors.length === 0 && (
            <Card className="mt-6 border-dashed border-2"><CardContent className="p-10 text-center"><Trophy className="w-10 h-10 mx-auto text-muted-foreground mb-3" /><div className="font-display font-bold">No approved vendors yet</div></CardContent></Card>
          )}
        </>
      )}
    </div>
  );
}
