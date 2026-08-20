import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty } from "@/components/ui/table";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Shield, User, Activity, ShieldCheck } from "lucide-react";

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
    <PageContainer>
      <PageHeader
        eyebrow="Admin · Compliance"
        title="Audit Log & DPDP Compliance"
        description="Every critical action is logged. DPDP Act (Digital Personal Data Protection) — India compliant."
      />

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
                <div className="cb-overline text-2xs">{s.label}</div>
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
        <Button onClick={load} className="font-bold" data-testid="audit-apply-btn">Apply</Button>
      </div>

      <Card className="mt-4 dashboard-card border-none overflow-hidden">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>When</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>User</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.entries.map((e, i) => (
                <TableRow key={e.audit_id} data-testid={`audit-row-${i}`}>
                  <TableCell className="text-xs whitespace-nowrap font-mono text-muted-foreground">{new Date(e.created_at).toLocaleString('en-IN')}</TableCell>
                  <TableCell><Badge variant="outline" className="font-mono text-2xs font-bold">{e.action}</Badge></TableCell>
                  <TableCell className="text-xs">
                    <div className="font-semibold">{e.user_email || "—"}</div>
                    <div className="text-muted-foreground capitalize">{e.user_role || "—"}</div>
                  </TableCell>
                  <TableCell className="text-xs font-mono">{e.ip_address || "—"}</TableCell>
                  <TableCell className="text-xs font-mono max-w-md truncate">{JSON.stringify(e.details || {})}</TableCell>
                </TableRow>
              ))}
              {data.entries.length === 0 && <TableEmpty colSpan={5}>No audit entries</TableEmpty>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
