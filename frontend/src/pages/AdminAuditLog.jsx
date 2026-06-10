import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Shield, User, Activity, Globe, ShieldCheck } from "lucide-react";

export default function AdminAuditLog() {
  const [data, setData] = useState({ entries: [], actions: [] });
  const [compliance, setCompliance] = useState(null);
  const [action, setAction] = useState("all");
  const [userId, setUserId] = useState("");

  const load = async () => {
    const params = {};
    if (action !== "all") params.action = action;
    if (userId) params.user_id = userId;
    const [a, c] = await Promise.all([
      api.get("/admin/audit-log", { params }),
      api.get("/admin/compliance-report"),
    ]);
    setData(a.data);
    setCompliance(c.data);
  };

  useEffect(() => { load(); }, [action]);

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="cb-overline text-accent">Admin · Compliance</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Audit Log & DPDP Compliance</h1>
      <p className="text-muted-foreground font-medium mt-1">Every critical action is logged. DPDP Act (Digital Personal Data Protection) — India compliant.</p>

      {compliance && (
        <div className="mt-6 grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { label: "Audit entries", val: compliance.audit_log_entries, icon: Activity },
            { label: "Total users", val: compliance.total_users, icon: User },
            { label: "Anonymised", val: compliance.deleted_users, icon: Shield },
            { label: "Deletion requests", val: compliance.pending_deletion_requests, icon: Shield },
            { label: "Retention (days)", val: compliance.data_retention_policy_days, icon: ShieldCheck },
          ].map(s => (
            <Card key={s.label} className="dashboard-card border-none" data-testid={`compliance-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <CardContent className="p-4">
                <div className="w-8 h-8 rounded-lg bg-accent/10 text-accent flex items-center justify-center mb-2"><s.icon className="w-4 h-4" /></div>
                <div className="cb-overline text-[10px]">{s.label}</div>
                <div className="font-display font-black text-xl tracking-tight">{s.val}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {compliance?.dpdp_compliant && (
        <Card className="mt-4 bg-emerald-50 border-emerald-200">
          <CardContent className="p-3 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-700" />
            <div className="text-sm font-bold text-emerald-900">DPDP Act 2023 compliant — Right to access, right to erasure, audit trail, data minimisation enabled.</div>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        <Select value={action} onValueChange={setAction}>
          <SelectTrigger className="w-64" data-testid="audit-action-filter"><SelectValue placeholder="All actions" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {data.actions.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="Filter by user_id" className="w-64" data-testid="audit-userid-filter" />
        <button onClick={load} className="px-4 py-2 bg-primary text-white rounded-md text-sm font-bold" data-testid="audit-apply-btn">Apply</button>
      </div>

      <Card className="mt-4 dashboard-card border-none overflow-hidden">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-secondary text-left text-xs cb-overline">
                <tr><th className="px-4 py-3">When</th><th className="px-4 py-3">Action</th><th className="px-4 py-3">User</th><th className="px-4 py-3">IP</th><th className="px-4 py-3">Details</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.entries.map((e, i) => (
                  <tr key={e.audit_id} className="hover:bg-secondary/40" data-testid={`audit-row-${i}`}>
                    <td className="px-4 py-3 text-xs whitespace-nowrap font-mono text-muted-foreground">{new Date(e.created_at).toLocaleString('en-IN')}</td>
                    <td className="px-4 py-3"><Badge variant="outline" className="font-mono text-[10px] font-bold">{e.action}</Badge></td>
                    <td className="px-4 py-3 text-xs">
                      <div className="font-semibold">{e.user_email || "—"}</div>
                      <div className="text-muted-foreground capitalize">{e.user_role || "—"}</div>
                    </td>
                    <td className="px-4 py-3 text-xs font-mono">{e.ip_address || "—"}</td>
                    <td className="px-4 py-3 text-xs font-mono max-w-md truncate">{JSON.stringify(e.details || {})}</td>
                  </tr>
                ))}
                {data.entries.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">No audit entries</td></tr>}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
