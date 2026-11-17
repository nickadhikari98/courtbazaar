import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { formatUsage } from "./usage";

/* Full-screen settings. Only settings the backend already supports have
   controls: profile name (PUT /auth/profile), notification channels
   (PUT /notifications/prefs) and the DPDP data rights (/dpdp/*). Panes with
   nothing supported yet show only their heading. */
const PANES = [
  ["account", "Account"], ["plan", "Plan and usage"], ["appearance", "Appearance"],
  ["language", "Language"], ["notifications", "Notifications"], ["privacy", "Privacy"],
];
const CHANNELS = [["email", "Email"], ["sms", "SMS"], ["whatsapp", "WhatsApp"]];
const PLAN_NAMES = { guest: "Guest", free: "Free", paid: "Paid" };

function Heading({ children }) {
  return <h2 className="font-display text-xl font-bold">{children}</h2>;
}

function AccountPane({ user, refresh }) {
  const [name, setName] = useState(user?.name || "");
  const [saving, setSaving] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/auth/profile", { name: name.trim() });
      await refresh?.();
      toast.success("Profile saved");
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't save your profile."));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form onSubmit={save} className="max-w-md space-y-5">
      <Heading>Account</Heading>
      <Avatar className="h-16 w-16">
        <AvatarImage src={user?.avatar_url} alt="" />
        <AvatarFallback className="text-lg font-semibold">{(user?.name || "?").slice(0, 1).toUpperCase()}</AvatarFallback>
      </Avatar>
      <div className="space-y-1.5">
        <Label htmlFor="settings-name">Full name</Label>
        <Input id="settings-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} data-testid="settings-name" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="settings-email">Email</Label>
        <Input id="settings-email" value={user?.email || ""} readOnly disabled data-testid="settings-email" />
      </div>
      <Button type="submit" disabled={saving || !name.trim() || name.trim() === user?.name} data-testid="settings-save">Save</Button>
    </form>
  );
}

function PlanPane({ usage }) {
  const text = formatUsage(usage);
  return (
    <div className="max-w-md space-y-3" data-testid="settings-plan">
      <Heading>Plan and usage</Heading>
      {usage && <p className="text-sm"><span className="font-semibold">Current plan:</span> {PLAN_NAMES[usage.plan] || usage.plan}</p>}
      {text && <p className="text-sm text-muted-foreground">{text.detail}</p>}
      {usage?.plan === "free" && <Link to="/subscription" className="text-sm font-semibold text-accent hover:underline">See paid plans</Link>}
    </div>
  );
}

function NotificationsPane({ user, refresh }) {
  const initial = { email: true, sms: true, whatsapp: true, ...(user?.notif_prefs || {}) }; // server default: all on
  const [prefs, setPrefs] = useState(initial);
  const toggle = async (key, value) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    try {
      await api.put("/notifications/prefs", next); // replaces the whole set, so send all three
      refresh?.();
    } catch (err) {
      setPrefs(prefs);
      toast.error(getErrorMessage(err, "Couldn't save that setting."));
    }
  };
  return (
    <div className="max-w-md space-y-4">
      <Heading>Notifications</Heading>
      {CHANNELS.map(([key, label]) => (
        <div key={key} className="flex items-center justify-between gap-4">
          <Label htmlFor={`settings-notif-${key}`}>{label} updates</Label>
          <Switch id={`settings-notif-${key}`} checked={!!prefs[key]} onCheckedChange={(v) => toggle(key, v)} data-testid={`settings-notif-${key}`} />
        </div>
      ))}
    </div>
  );
}

function PrivacyPane() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const download = async () => {
    try {
      const { data } = await api.get("/dpdp/my-data/download", { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = Object.assign(document.createElement("a"), { href: url, download: "my-courtbazaar-data.json" });
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't download your data."));
    }
  };
  const requestDeletion = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/dpdp/request-deletion", { reason: "Requested from chat settings" });
      toast.success(data?.message || "Your deletion request has been recorded.");
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't record your request."));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };
  return (
    <div className="max-w-md space-y-4">
      <Heading>Privacy</Heading>
      <div className="space-y-1">
        <Button type="button" variant="outline" onClick={download} data-testid="settings-download-data">Download my data</Button>
        <p className="text-xs text-muted-foreground">A copy of the personal data CourtBazaar holds about you.</p>
      </div>
      <div className="space-y-1">
        <Button type="button" variant="outline" className="text-destructive" onClick={() => setConfirming(true)} data-testid="settings-request-deletion">
          Request account deletion
        </Button>
        <p className="text-xs text-muted-foreground">Our team processes deletion requests within 30 days.</p>
      </div>
      <ConfirmDialog
        open={confirming} onOpenChange={setConfirming} busy={busy}
        title="Request account deletion?" description="We'll delete your account and its data within 30 days. This can't be undone once processed."
        confirmLabel="Request deletion" onConfirm={requestDeletion}
      />
    </div>
  );
}

export default function SettingsDialog({ open, onOpenChange, usage, initialPane = "account" }) {
  const { user, refresh } = useAuth() || {};
  const [pane, setPane] = useState(initialPane);
  useEffect(() => { if (open) setPane(initialPane); }, [open, initialPane]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="h-[100dvh] max-h-none w-screen max-w-none gap-0 overflow-hidden rounded-none p-0 sm:rounded-none [&>button:last-child]:hidden"
        aria-describedby={undefined} data-testid="settings-dialog"
      >
        <Tabs value={pane} onValueChange={setPane} orientation="vertical" className="flex h-full min-h-0 flex-col md:flex-row">
          <div className="shrink-0 border-b border-border bg-muted/40 md:w-60 md:border-b-0 md:border-r">
            <div className="flex items-center justify-between px-4 py-3">
              <DialogTitle className="font-display text-lg">Settings</DialogTitle>
              <DialogClose asChild>
                <Button type="button" variant="ghost" size="sm" data-testid="settings-close"><X className="mr-1 h-4 w-4" />Close</Button>
              </DialogClose>
            </div>
            <TabsList className="flex h-auto w-full justify-start gap-1 overflow-x-auto bg-transparent px-2 pb-2 md:flex-col md:items-stretch md:overflow-visible">
              {PANES.map(([value, label]) => (
                <TabsTrigger key={value} value={value} className="justify-start px-3 py-2 data-[state=active]:bg-background" data-testid={`settings-tab-${value}`}>
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto cb-scroll p-6">
            <TabsContent value="account" className="mt-0"><AccountPane user={user} refresh={refresh} /></TabsContent>
            <TabsContent value="plan" className="mt-0"><PlanPane usage={usage} /></TabsContent>
            {/* No dark design tokens exist yet, so there's no theme to switch to. */}
            <TabsContent value="appearance" className="mt-0"><Heading>Appearance</Heading></TabsContent>
            <TabsContent value="language" className="mt-0"><Heading>Language</Heading></TabsContent>
            <TabsContent value="notifications" className="mt-0"><NotificationsPane user={user} refresh={refresh} /></TabsContent>
            <TabsContent value="privacy" className="mt-0"><PrivacyPane /></TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
