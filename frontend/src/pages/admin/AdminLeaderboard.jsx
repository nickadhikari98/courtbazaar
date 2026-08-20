import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Trophy, Crown, Award } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import EmptyState from "@/components/shared/EmptyState";
import Loading from "@/components/shared/Loading";

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
    <PageContainer>
      <PageHeader
        eyebrow="Admin · Performance"
        title="Vendor leaderboard & SLA"
        description="Ranked by composite SLA score (on-time × 35% + completion × 25% + rating × 25% + dispute-free × 15%)"
      />

      {loading ? <Loading className="mt-6" /> : (
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
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rank</TableHead>
                      <TableHead>Vendor</TableHead>
                      <TableHead>Grade</TableHead>
                      <TableHead className="text-right">SLA</TableHead>
                      <TableHead className="text-right">On-time</TableHead>
                      <TableHead className="text-right">Avg TAT</TableHead>
                      <TableHead className="text-right">Rating</TableHead>
                      <TableHead className="text-right">Orders</TableHead>
                      <TableHead className="text-right">Revenue</TableHead>
                      <TableHead className="text-right">Disputes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rest.map((v, i) => (
                      <TableRow key={v.vendor_id} data-testid={`leaderboard-row-${i}`}>
                        <TableCell className="font-mono font-bold">{i + 4}</TableCell>
                        <TableCell>
                          <div className="font-display font-bold flex items-center gap-1.5">{v.shop_name}
                            {v.sponsored && <Crown className="w-3.5 h-3.5 text-accent fill-accent" />}
                          </div>
                          <div className="text-xs text-muted-foreground">{v.city} · {v.court_count} courts</div>
                        </TableCell>
                        <TableCell><Badge className={`${gradeColors[v.grade]} border-0 font-black`}>{v.grade}</Badge></TableCell>
                        <TableCell className="text-right font-bold">{v.sla_score}</TableCell>
                        <TableCell className="text-right">{v.on_time_rate}%</TableCell>
                        <TableCell className="text-right">{v.avg_turnaround_hours}h</TableCell>
                        <TableCell className="text-right">{v.avg_rating ? `${v.avg_rating}/5` : "—"}</TableCell>
                        <TableCell className="text-right font-semibold">{v.total_orders}</TableCell>
                        <TableCell className="text-right font-semibold">{formatINR(v.revenue)}</TableCell>
                        <TableCell className="text-right">{v.dispute_rate}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {vendors.length === 0 && <EmptyState className="mt-6" icon={Trophy} title="No approved vendors yet" />}
        </>
      )}
    </PageContainer>
  );
}
