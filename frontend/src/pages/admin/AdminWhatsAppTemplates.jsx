import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Send, CheckCircle2, XCircle, Plus, FileText, Trash2, Clock } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import EmptyState from "@/components/shared/EmptyState";

const statusStyle = {
  draft: "bg-secondary text-foreground",
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
};

export default function AdminWhatsAppTemplates() {
  const [tmpls, setTmpls] = useState([]);
  const [status, setStatus] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [activeT, setActiveT] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [form, setForm] = useState({ name: "", category: "transactional", language: "en", body: "", variables: "", description: "" });

  const load = async () => {
    const params = status !== "all" ? { status_filter: status } : {};
    const { data } = await api.get("/admin/whatsapp-templates", { params });
    setTmpls(data || []);
  };
  useEffect(() => { load(); }, [status]);

  const create = async () => {
    if (!form.name || !form.body) { toast.error("Name + body required"); return; }
    try {
      await api.post("/admin/whatsapp-templates", {
        ...form,
        variables: form.variables.split(",").map(s => s.trim()).filter(Boolean),
      });
      toast.success("Template created as draft");
      setCreateOpen(false);
      setForm({ name: "", category: "transactional", language: "en", body: "", variables: "", description: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const submit = async (id) => {
    try {
      const { data } = await api.post(`/admin/whatsapp-templates/${id}/submit`);
      toast.success(`Submitted ${data.twilio_sid ? `· SID ${data.twilio_sid}` : '(mock — wire Twilio for real submission)'}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const approve = async (id) => {
    try {
      await api.post(`/admin/whatsapp-templates/${id}/approve`);
      toast.success("Approved");
      load();
    } catch { toast.error("Failed"); }
  };

  const reject = async () => {
    try {
      await api.post(`/admin/whatsapp-templates/${activeT.template_id}/reject`, { reason: rejectReason });
      toast.success("Rejected");
      setRejectOpen(false);
      setRejectReason("");
      load();
    } catch { toast.error("Failed"); }
  };

  const del = async (id) => {
    if (!confirm("Delete this template?")) return;
    try {
      await api.delete(`/admin/whatsapp-templates/${id}`);
      toast.success("Deleted");
      load();
    } catch { toast.error("Failed"); }
  };

  return (
    <PageContainer className="max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <div className="cb-overline text-accent">Admin · WhatsApp</div>
          <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Template approval workflow</h1>
          <p className="text-muted-foreground font-medium mt-1">Draft → Submit → Twilio/Meta approval → Approved · Reject anytime</p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button className="bg-accent font-bold" data-testid="create-template-btn"><Plus className="w-4 h-4 mr-1.5" /> New template</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Create WhatsApp template</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label>Name (unique slug)</Label><Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} placeholder="order_delivered_v1" data-testid="tmpl-name-input" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Category</Label>
                  <Select value={form.category} onValueChange={(v) => setForm({...form, category: v})}>
                    <SelectTrigger data-testid="tmpl-category-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="transactional">Transactional</SelectItem>
                      <SelectItem value="marketing">Marketing</SelectItem>
                      <SelectItem value="otp">OTP / Authentication</SelectItem>
                      <SelectItem value="utility">Utility</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Language</Label>
                  <Select value={form.language} onValueChange={(v) => setForm({...form, language: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="hi">Hindi</SelectItem>
                      <SelectItem value="ta">Tamil</SelectItem>
                      <SelectItem value="te">Telugu</SelectItem>
                      <SelectItem value="mr">Marathi</SelectItem>
                      <SelectItem value="bn">Bengali</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div><Label>Body (use {"{{1}}, {{2}}"} for variables)</Label>
                <Textarea value={form.body} onChange={(e) => setForm({...form, body: e.target.value})} rows={5} placeholder="Hi {{1}}, your order {{2}} has been delivered. Rate at courtbazaar.com" data-testid="tmpl-body-input" />
              </div>
              <div><Label>Variables (comma-separated)</Label><Input value={form.variables} onChange={(e) => setForm({...form, variables: e.target.value})} placeholder="name, order_id" data-testid="tmpl-vars-input" /></div>
              <div><Label>Description</Label><Input value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} /></div>
            </div>
            <DialogFooter><Button onClick={create} className="bg-accent font-bold" data-testid="tmpl-create-submit">Create draft</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Tabs value={status} onValueChange={setStatus} className="mb-4">
        <TabsList data-testid="tmpl-tabs">
          <TabsTrigger value="all" data-testid="tab-all">All</TabsTrigger>
          <TabsTrigger value="draft" data-testid="tab-draft">Draft</TabsTrigger>
          <TabsTrigger value="pending" data-testid="tab-pending">Pending</TabsTrigger>
          <TabsTrigger value="approved" data-testid="tab-approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected" data-testid="tab-rejected">Rejected</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="space-y-3">
        {tmpls.length === 0 && <EmptyState icon={FileText} title="No templates" />}
        {tmpls.map(t => (
          <Card key={t.template_id} className="dashboard-card border-none" data-testid={`template-${t.template_id}`}>
            <CardContent className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-display font-bold text-base">{t.name}</span>
                    <Badge className={`${statusStyle[t.status]} border-0 font-bold uppercase text-2xs`} data-testid={`status-${t.template_id}`}>{t.status}</Badge>
                    <Badge variant="outline" className="text-2xs uppercase font-bold">{t.category}</Badge>
                    <Badge variant="outline" className="text-2xs uppercase font-bold">{t.language}</Badge>
                  </div>
                  {t.description && <div className="text-xs text-muted-foreground font-semibold mt-1">{t.description}</div>}
                </div>
                <div className="flex gap-1.5">
                  {t.status === "draft" && (
                    <Button onClick={() => submit(t.template_id)} variant="outline" size="sm" className="font-bold" data-testid={`submit-${t.template_id}`}>
                      <Send className="w-3 h-3 mr-1" /> Submit
                    </Button>
                  )}
                  {t.status === "pending" && (
                    <>
                      <Button onClick={() => approve(t.template_id)} size="sm" className="bg-emerald-600 hover:bg-emerald-700 font-bold" data-testid={`approve-${t.template_id}`}>
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Approve
                      </Button>
                      <Button onClick={() => { setActiveT(t); setRejectOpen(true); }} size="sm" variant="outline" className="text-rose-700 border-rose-300 font-bold" data-testid={`reject-${t.template_id}`}>
                        <XCircle className="w-3 h-3 mr-1" /> Reject
                      </Button>
                    </>
                  )}
                  {(t.status === "draft" || t.status === "rejected") && (
                    <Button onClick={() => del(t.template_id)} size="sm" variant="outline" className="text-destructive border-destructive/30" data-testid={`del-${t.template_id}`}>
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              </div>
              <div className="bg-secondary rounded-lg p-3 text-sm font-mono leading-relaxed">{t.body}</div>
              {t.variables?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {t.variables.map((v, i) => <Badge key={i} variant="outline" className="text-2xs font-bold font-mono">{"{{" + (i+1) + "}} = " + v}</Badge>)}
                </div>
              )}
              {t.twilio_sid && <div className="mt-2 text-xs font-mono text-muted-foreground">Twilio SID: {t.twilio_sid}</div>}
              {t.rejection_reason && <div className="mt-2 text-xs text-rose-700 font-semibold">Rejection: {t.rejection_reason}</div>}
              {t.history?.length > 0 && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer cb-overline">History ({t.history.length})</summary>
                  <div className="mt-1 space-y-1 pl-3">
                    {t.history.map((h, i) => (
                      <div key={i} className="flex items-center gap-2 text-muted-foreground"><Clock className="w-3 h-3" /> <b>{h.action}</b> by {h.by} · {new Date(h.at).toLocaleString('en-IN')}</div>
                    ))}
                  </div>
                </details>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reject template</DialogTitle></DialogHeader>
          <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Reason for rejection" data-testid="reject-reason-input" />
          <DialogFooter><Button onClick={reject} className="bg-rose-600 font-bold" data-testid="reject-submit">Reject</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
