import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ChevronRight, X } from "lucide-react";
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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { resetTime } from "./usage";

/* Chat settings: a centred modal over the chat (900px x 80vh, left nav and a
   pane); under 768px a full-screen sheet whose first screen is the nav, with a
   back arrow from each pane. Only settings with a backend (or that are purely
   this browser's chat preferences) have controls. */
export const PANES = [
  ["account", "Account"], ["usage", "Usage"], ["appearance", "Appearance"],
  ["language", "Language"], ["notifications", "Notifications"], ["privacy", "Privacy"],
];
const PLAN_NAMES = { guest: "Guest", free: "Free", paid: "Paid" };
export const LANGUAGES = [
  ["auto", "Auto (match my message)"], ["en", "English"], ["hi", "Hindi"], ["hinglish", "Hinglish"],
];
const WIDTHS = [["narrow", "Narrow"], ["wide", "Wide"]];

function Heading({ children }) {
  return <h2 className="mb-4 font-display text-xl font-bold">{children}</h2>;
}

export const WORK_TYPES = ["Advocate", "Law firm", "Corporate counsel", "Law student", "Other"];
const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"];
const AVATAR_MAX_BYTES = 10 * 1024 * 1024;

function AccountPane({ user, refresh }) {
  const [form, setForm] = useState({ name: user?.name || "", display_name: user?.display_name || "", work_type: user?.work_type || "" });
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  // Only fields that changed are sent (PUT /auth/profile ignores the rest).
  const changes = Object.fromEntries(Object.entries(form)
    .map(([k, v]) => [k, v.trim()]).filter(([k, v]) => v && v !== (user?.[k] || "")));
  const changed = Object.keys(changes).length > 0;
  const uploadPhoto = async (file) => {
    if (!file) return;
    if (!AVATAR_TYPES.includes(file.type)) { toast.error("Profile photos must be PNG, JPEG, or WebP."); return; }
    if (file.size > AVATAR_MAX_BYTES) { toast.error("That photo is over 10MB."); return; }
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      await api.post("/auth/profile/avatar", body);
      await refresh?.();
      toast.success("Photo updated");
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't upload that photo."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/auth/profile", changes);
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
      <div className="flex items-center gap-4">
        <Avatar className="h-16 w-16">
          <AvatarImage src={user?.avatar_url} alt="" />
          <AvatarFallback className="text-lg font-semibold">{(user?.name || "?").slice(0, 1).toUpperCase()}</AvatarFallback>
        </Avatar>
        <div>
          <input ref={fileRef} type="file" accept={AVATAR_TYPES.join(",")} className="sr-only" id="settings-photo"
            onChange={(e) => uploadPhoto(e.target.files?.[0])} data-testid="settings-photo-input" />
          <Button type="button" variant="outline" size="sm" className="h-10" disabled={uploading}
            onClick={() => fileRef.current?.click()} data-testid="settings-photo">
            {uploading ? "Uploading…" : "Upload photo"}
          </Button>
          <p className="mt-1 text-xs text-muted-foreground">PNG, JPEG, or WebP, up to 10MB</p>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="settings-name">Full name</Label>
        <Input id="settings-name" value={form.name} onChange={(e) => set("name")(e.target.value)} maxLength={120} data-testid="settings-name" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="settings-display-name">What should we call you?</Label>
        <Input id="settings-display-name" value={form.display_name} onChange={(e) => set("display_name")(e.target.value)} maxLength={40} data-testid="settings-display-name" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="settings-work-type">What best describes your work?</Label>
        <Select value={form.work_type || undefined} onValueChange={set("work_type")}>
          <SelectTrigger id="settings-work-type" data-testid="settings-work-type"><SelectValue placeholder="Choose one" /></SelectTrigger>
          <SelectContent>
            {WORK_TYPES.map((w) => <SelectItem key={w} value={w}>{w}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="settings-email">Email</Label>
        <Input id="settings-email" value={user?.email || ""} readOnly disabled data-testid="settings-email" />
      </div>
      <Button type="submit" disabled={saving || !changed} data-testid="settings-save">Save</Button>
    </form>
  );
}

function Row({ label, children }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2.5 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span><span className="text-right font-medium tabular-nums">{children}</span>
    </div>
  );
}

/* Straight from GET /ai/usage: a limit the endpoint returns as null is shown as
   "No daily limit", never as a number. */
function UsagePane({ usage }) {
  const count = (used, limit) => (typeof used !== "number" ? null
    : typeof limit === "number" ? `${used.toLocaleString()} / ${limit.toLocaleString()}` : `${used.toLocaleString()} (no daily limit)`);
  const reset = resetTime(usage?.resets_at);
  return (
    <div className="max-w-md" data-testid="settings-usage">
      <Heading>Usage</Heading>
      {usage ? (
        <>
          <Row label="Plan">{PLAN_NAMES[usage.plan] || usage.plan}</Row>
          {count(usage.messages_used, usage.messages_limit) && <Row label="Requests today">{count(usage.messages_used, usage.messages_limit)}</Row>}
          {count(usage.tokens_used, usage.tokens_limit) && <Row label="Tokens today">{count(usage.tokens_used, usage.tokens_limit)}</Row>}
          {reset && <Row label="Resets at">{reset}</Row>}
          {usage.plan === "free" && (
            <Button asChild className="mt-4"><Link to="/subscription" data-testid="settings-upgrade">Upgrade</Link></Button>
          )}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Usage isn't available right now.</p>
      )}
    </div>
  );
}

function Choice({ name, options, value, onChange, testId }) {
  return (
    <RadioGroup value={value} onValueChange={onChange} className="space-y-2" aria-label={name} data-testid={testId}>
      {options.map(([v, label]) => (
        <div key={v} className="flex items-center gap-3">
          <RadioGroupItem value={v} id={`${testId}-${v}`} data-testid={`${testId}-${v}`} />
          <Label htmlFor={`${testId}-${v}`} className="font-normal">{label}</Label>
        </div>
      ))}
    </RadioGroup>
  );
}

function NotificationsPane({ user, refresh }) {
  const initial = { email: true, sms: true, whatsapp: true, ...(user?.notif_prefs || {}) }; // server default: all on
  const [prefs, setPrefs] = useState(initial);
  const toggle = async (key, value) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    try {
      // The endpoint replaces the whole set: WhatsApp has no toggle here but keeps its current value.
      await api.put("/notifications/prefs", next);
      refresh?.();
    } catch (err) {
      setPrefs(prefs);
      toast.error(getErrorMessage(err, "Couldn't save that setting."));
    }
  };
  return (
    <div className="max-w-md space-y-4">
      <Heading>Notifications</Heading>
      {[["email", "Email"], ["sms", "SMS"]].map(([key, label]) => (
        <div key={key} className="flex items-center justify-between gap-4">
          <Label htmlFor={`settings-notif-${key}`}>{label} updates</Label>
          <Switch id={`settings-notif-${key}`} checked={!!prefs[key]} onCheckedChange={(v) => toggle(key, v)} data-testid={`settings-notif-${key}`} />
        </div>
      ))}
    </div>
  );
}

function PrivacyPane({ onChatsDeleted, onGetHelp }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const download = async () => {
    try {
      const { data } = await api.get("/dpdp/my-data/download", { responseType: "blob" });
      const url = URL.createObjectURL(data);
      Object.assign(document.createElement("a"), { href: url, download: "my-courtbazaar-data.json" }).click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't download your data."));
    }
  };
  const deleteAll = async () => {
    setBusy(true);
    try {
      await api.delete("/ai/chats");
      onChatsDeleted?.();
      toast.success("All chats deleted");
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't delete your chats. Please try again."));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };
  return (
    <div className="max-w-md space-y-5">
      <Heading>Privacy</Heading>
      <div className="space-y-1">
        <Button type="button" variant="outline" onClick={download} data-testid="settings-download-data">Download my data</Button>
        <p className="text-xs text-muted-foreground">A copy of the personal data CourtBazaar holds about you.</p>
      </div>
      <div className="space-y-1">
        <Button type="button" variant="outline" className="text-destructive" onClick={() => setConfirming(true)} data-testid="settings-delete-chats">
          Delete all chats
        </Button>
        <p className="text-xs text-muted-foreground">Removes every Instant Legal Help chat, archived ones included.</p>
      </div>
      <p className="text-sm text-muted-foreground" data-testid="settings-account-deletion">
        To delete your CourtBazaar account, write to{" "}
        <button type="button" onClick={onGetHelp} className="font-semibold text-accent hover:underline">support</button>.
      </p>
      <ConfirmDialog
        open={confirming} onOpenChange={setConfirming} busy={busy}
        title="Delete all chats?" description="Every chat will be permanently deleted. This can't be undone."
        confirmLabel="Delete all" onConfirm={deleteAll}
      />
    </div>
  );
}

export default function SettingsDialog({ open, onOpenChange, pane, usage, prefs, setPref, onChatsDeleted, onGetHelp }) {
  const { user, refresh } = useAuth() || {};
  const [active, setActive] = useState(pane || "account");
  // Mobile: the nav is the first screen unless a menu item asked for a pane.
  const [showPane, setShowPane] = useState(!!pane);
  useEffect(() => {
    if (open) { setActive(pane || "account"); setShowPane(!!pane); }
  }, [open, pane]);
  const choose = (value) => { setActive(value); setShowPane(true); };
  const title = PANES.find(([v]) => v === active)?.[1];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={"flex h-[80vh] w-[calc(100vw-2rem)] max-w-[900px] gap-0 overflow-hidden rounded-2xl p-0 "
          + "max-md:inset-0 max-md:left-0 max-md:top-0 max-md:h-[100dvh] max-md:w-screen max-md:max-w-none max-md:translate-x-0 "
          + "max-md:translate-y-0 max-md:rounded-none max-md:border-0 [&>button:last-child]:hidden"}
        aria-describedby={undefined} data-testid="settings-dialog"
      >
        <Tabs value={active} onValueChange={choose} orientation="vertical" activationMode="manual" className="flex h-full min-h-0 w-full">
          <div className={`w-full shrink-0 border-border bg-muted/40 md:flex md:w-56 md:flex-col md:border-r ${showPane ? "max-md:hidden" : ""}`}>
            <div className="flex items-center justify-between px-4 py-3">
              <DialogTitle className="font-display text-lg">Settings</DialogTitle>
              <DialogClose asChild>
                <Button type="button" variant="ghost" size="sm" className="h-10" data-testid="settings-close"><X className="mr-1 h-4 w-4" />Close</Button>
              </DialogClose>
            </div>
            <TabsList className="flex h-auto w-full flex-col items-stretch gap-1 bg-transparent px-2 pb-2">
              {PANES.map(([value, label]) => (
                <TabsTrigger key={value} value={value} className="h-10 justify-between px-3 data-[state=active]:bg-background md:justify-start" data-testid={`settings-tab-${value}`}>
                  {label}<ChevronRight className="h-4 w-4 text-muted-foreground md:hidden" aria-hidden="true" />
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className={`min-h-0 flex-1 flex-col ${showPane ? "flex" : "max-md:hidden md:flex"}`}>
            <div className="flex items-center gap-1 border-b border-border px-2 py-2 md:hidden">
              <button type="button" onClick={() => setShowPane(false)} aria-label="Back to settings"
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg hover:bg-muted" data-testid="settings-back">
                <ArrowLeft className="h-5 w-5" />
              </button>
              <span className="font-semibold">{title}</span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto cb-scroll p-6">
              <TabsContent value="account" className="mt-0"><AccountPane user={user} refresh={refresh} /></TabsContent>
              <TabsContent value="usage" className="mt-0"><UsagePane usage={usage} /></TabsContent>
              <TabsContent value="appearance" className="mt-0">
                <Heading>Appearance</Heading>
                <p className="mb-2 text-sm font-semibold">Transcript width</p>
                <Choice name="Transcript width" options={WIDTHS} value={prefs.width} onChange={(v) => setPref("width", v)} testId="settings-width" />
              </TabsContent>
              <TabsContent value="language" className="mt-0">
                <Heading>Language</Heading>
                <p className="mb-3 text-sm text-muted-foreground">The language answers are written in.</p>
                <Choice name="Answer language" options={LANGUAGES} value={prefs.language} onChange={(v) => setPref("language", v)} testId="settings-language" />
              </TabsContent>
              <TabsContent value="notifications" className="mt-0"><NotificationsPane user={user} refresh={refresh} /></TabsContent>
              <TabsContent value="privacy" className="mt-0"><PrivacyPane onChatsDeleted={onChatsDeleted} onGetHelp={onGetHelp} /></TabsContent>
            </div>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
