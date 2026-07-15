import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Users, UserPlus, Trash2, Crown, ShieldCheck, Briefcase, Building2 } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";

const roleIcons = { owner: Crown, partner: ShieldCheck, associate: Briefcase, paralegal: Users };
const roleLabels = { owner: "Owner", partner: "Partner", associate: "Associate", paralegal: "Paralegal" };

export default function FirmManagement() {
  const { user, refresh } = useAuth();
  const [firmData, setFirmData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", gst: "", address: "" });
  const [inviteForm, setInviteForm] = useState({ email: "", name: "", role: "associate" });
  const [inviteToken, setInviteToken] = useState("");

  const load = async () => {
    setLoading(true);
    const { data } = await api.get("/firms/me");
    setFirmData(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const createFirm = async () => {
    if (!createForm.name) { toast.error("Firm name required"); return; }
    try {
      await api.post("/firms", createForm);
      toast.success("Firm created!");
      setCreateOpen(false);
      await refresh();
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const sendInvite = async () => {
    if (!inviteForm.email) { toast.error("Email required"); return; }
    try {
      await api.post("/firms/invite", { ...inviteForm, firm_id: firmData.firm.firm_id });
      toast.success("Invite sent!");
      setInviteOpen(false);
      setInviteForm({ email: "", name: "", role: "associate" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const acceptInvite = async () => {
    try {
      await api.post("/firms/accept-invite", { token: inviteToken });
      toast.success("Joined firm!");
      setAcceptOpen(false);
      await refresh();
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Invalid token"); }
  };

  const removeMember = async (uid) => {
    if (!confirm("Remove this member?")) return;
    try {
      await api.delete(`/firms/${firmData.firm.firm_id}/members/${uid}`);
      toast.success("Member removed");
      load();
    } catch { toast.error("Failed"); }
  };

  if (loading) return <div className="p-10">Loading…</div>;

  if (!firmData?.onboarded) {
    return (
      <PageContainer className="max-w-3xl">
        <div className="cb-overline text-accent">Law firm</div>
        <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Set up your firm or join one</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="dashboard-card border-none">
            <CardContent className="p-6">
              <Building2 className="w-10 h-10 text-accent mb-3" />
              <div className="font-display font-bold text-xl">Create a new firm</div>
              <p className="text-sm text-muted-foreground font-medium mt-1">You become the owner. Invite partners, associates, paralegals.</p>
              <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogTrigger asChild>
                  <Button className="mt-4 bg-primary font-bold" data-testid="create-firm-btn">Create firm</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Create your firm</DialogTitle></DialogHeader>
                  <div className="space-y-3">
                    <div><Label>Firm name</Label><Input value={createForm.name} onChange={(e) => setCreateForm({...createForm, name: e.target.value})} placeholder="Sinha & Associates" data-testid="firm-name-input" /></div>
                    <div><Label>GST (optional)</Label><Input value={createForm.gst} onChange={(e) => setCreateForm({...createForm, gst: e.target.value})} placeholder="07AAACS1234A1Z5" /></div>
                    <div><Label>Address</Label><Input value={createForm.address} onChange={(e) => setCreateForm({...createForm, address: e.target.value})} /></div>
                  </div>
                  <DialogFooter><Button onClick={createFirm} className="bg-primary font-bold" data-testid="firm-create-submit">Create</Button></DialogFooter>
                </DialogContent>
              </Dialog>
            </CardContent>
          </Card>

          <Card className="dashboard-card border-none">
            <CardContent className="p-6">
              <UserPlus className="w-10 h-10 text-accent mb-3" />
              <div className="font-display font-bold text-xl">Join an existing firm</div>
              <p className="text-sm text-muted-foreground font-medium mt-1">Got an invite token from your firm owner? Paste it below.</p>
              <Dialog open={acceptOpen} onOpenChange={setAcceptOpen}>
                <DialogTrigger asChild>
                  <Button className="mt-4 bg-accent font-bold" data-testid="accept-invite-btn">Accept invite</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Accept firm invite</DialogTitle></DialogHeader>
                  <div><Label>Invite token</Label><Input value={inviteToken} onChange={(e) => setInviteToken(e.target.value)} placeholder="Paste token" data-testid="invite-token-input" /></div>
                  <DialogFooter><Button onClick={acceptInvite} className="bg-accent font-bold" data-testid="invite-accept-submit">Accept</Button></DialogFooter>
                </DialogContent>
              </Dialog>
            </CardContent>
          </Card>
        </div>
      </PageContainer>
    );
  }

  const isOwner = firmData.my_role === "owner";
  const canInvite = ["owner", "partner"].includes(firmData.my_role);

  return (
    <PageContainer className="max-w-5xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <PageHeader eyebrow="Law firm" title={firmData.firm.name} />
          <div className="text-sm text-muted-foreground font-semibold mt-1">{firmData.firm.gst && `GST: ${firmData.firm.gst}`}</div>
        </div>
        {canInvite && (
          <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
            <DialogTrigger asChild>
              <Button className="bg-accent font-bold" data-testid="invite-member-btn"><UserPlus className="w-4 h-4 mr-1.5" /> Invite member</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Invite team member</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>Name</Label><Input value={inviteForm.name} onChange={(e) => setInviteForm({...inviteForm, name: e.target.value})} data-testid="invite-name-input" /></div>
                <div><Label>Email</Label><Input type="email" value={inviteForm.email} onChange={(e) => setInviteForm({...inviteForm, email: e.target.value})} data-testid="invite-email-input" /></div>
                <div><Label>Role</Label>
                  <Select value={inviteForm.role} onValueChange={(v) => setInviteForm({...inviteForm, role: v})}>
                    <SelectTrigger data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="partner">Partner — can invite + manage orders</SelectItem>
                      <SelectItem value="associate">Associate — can place orders</SelectItem>
                      <SelectItem value="paralegal">Paralegal — view-only / uploads</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter><Button onClick={sendInvite} className="bg-accent font-bold" data-testid="invite-submit-btn">Send invite</Button></DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card className="dashboard-card border-none mb-6">
        <CardContent className="p-6">
          <div className="cb-overline mb-3">Team ({firmData.members.length})</div>
          <div className="space-y-2">
            {firmData.members.map(m => {
              const Icon = roleIcons[m.role] || Users;
              const initials = (m.name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase();
              return (
                <div key={m.user_id} className="flex items-center gap-4 p-3 hover:bg-secondary rounded-lg" data-testid={`firm-member-${m.user_id}`}>
                  <Avatar className="w-10 h-10"><AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback></Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-bold">{m.name}</div>
                    <div className="text-xs text-muted-foreground">{m.email}</div>
                  </div>
                  <Badge className="bg-accent/10 text-accent border-0 font-bold flex items-center gap-1.5"><Icon className="w-3 h-3" /> {roleLabels[m.role]}</Badge>
                  {isOwner && m.role !== "owner" && (
                    <button onClick={() => removeMember(m.user_id)} className="p-2 text-destructive hover:bg-destructive/10 rounded-lg" data-testid={`remove-member-${m.user_id}`}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-accent/5 border-accent/30">
        <CardContent className="p-5 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-accent mt-0.5" />
          <div>
            <div className="font-display font-bold text-sm">Role-based permissions</div>
            <div className="text-xs text-muted-foreground font-medium mt-1">
              <b>Owner</b>: full control · <b>Partner</b>: invite + manage orders + view billing · <b>Associate</b>: place + track orders · <b>Paralegal</b>: upload + view-only
            </div>
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
