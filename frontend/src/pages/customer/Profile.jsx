import React, { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { toast } from "sonner";
import { Loader2, User, ShieldCheck } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import CapabilitiesCard from "@/components/shared/CapabilitiesCard";

export default function Profile() {
  const { user, refresh } = useAuth();
  const [form, setForm] = useState({
    name: user?.name || "",
    phone: user?.phone || "",
    bar_council_id: user?.bar_council_id || "",
    chamber_address: user?.chamber_address || "",
    chamber_court: user?.chamber_court || "",
    gst_number: user?.gst_number || "",
  });
  const [loading, setLoading] = useState(false);

  const save = async () => {
    setLoading(true);
    try {
      await api.put("/auth/profile", form);
      toast.success("Profile updated");
      await refresh();
    } catch { toast.error("Update failed"); }
    finally { setLoading(false); }
  };

  const initials = (form.name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase();

  return (
    <PageContainer className="max-w-3xl">
      <PageHeader eyebrow="Profile" title="Your account" className="mb-6" />

      <Card className="dashboard-card border-none mb-6">
        <CardContent className="p-6 flex items-center gap-5">
          <Avatar className="w-20 h-20">
            <AvatarImage src={user?.avatar_url} />
            <AvatarFallback className="bg-primary text-white text-xl font-bold">{initials}</AvatarFallback>
          </Avatar>
          <div>
            <div className="font-display font-bold text-2xl">{user?.name}</div>
            <div className="text-sm text-muted-foreground font-semibold">{user?.email}</div>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className="cb-overline">Role</span> <span className="font-bold capitalize">{user?.role?.replace('_', ' ')}</span>
              {user?.verified && <span className="flex items-center gap-1 text-emerald-700 font-bold"><ShieldCheck className="w-3.5 h-3.5" /> Verified</span>}
            </div>
          </div>
        </CardContent>
      </Card>

      {user?.role === "advocate" && <CapabilitiesCard user={user} />}

      <Card className="dashboard-card border-none">
        <CardContent className="p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} data-testid="profile-name" /></div>
            <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value})} data-testid="profile-phone" /></div>
          </div>
          {user?.role === "advocate" && (
            <>
              <div><Label>Bar Council Registration #</Label><Input value={form.bar_council_id} onChange={(e) => setForm({...form, bar_council_id: e.target.value})} placeholder="D/1234/2018" data-testid="profile-bar-id" /></div>
              <div><Label>Chamber Address</Label><Textarea value={form.chamber_address} onChange={(e) => setForm({...form, chamber_address: e.target.value})} placeholder="Chamber no., court complex, city, PIN" data-testid="profile-chamber" /></div>
            </>
          )}
          <div><Label>GST Number (optional)</Label><Input value={form.gst_number} onChange={(e) => setForm({...form, gst_number: e.target.value})} placeholder="22AAAAA0000A1Z5" data-testid="profile-gst" /></div>
          <Button onClick={save} disabled={loading} className="bg-primary font-bold" data-testid="profile-save-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            Save changes
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
