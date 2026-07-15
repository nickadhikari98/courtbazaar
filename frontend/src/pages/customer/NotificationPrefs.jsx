import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Bell, Mail, MessageSquare, Phone, ShieldCheck, AlertCircle } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function NotificationPrefs() {
  const { user, refresh } = useAuth();
  const [prefs, setPrefs] = useState(user?.notif_prefs || { sms: true, whatsapp: true, email: true });
  const [status, setStatus] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.get("/notifications/status").then(r => setStatus(r.data)); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/notifications/prefs", prefs);
      toast.success("Preferences saved");
      await refresh();
    } catch { toast.error("Failed"); }
    finally { setSaving(false); }
  };

  const channels = [
    { key: "sms", label: "SMS", desc: "Order updates via Twilio", icon: Phone, enabled: status.sms_enabled },
    { key: "whatsapp", label: "WhatsApp", desc: "Rich updates via Twilio WhatsApp Business", icon: MessageSquare, enabled: status.whatsapp_enabled },
    { key: "email", label: "Email", desc: "GST invoices + summaries via SendGrid", icon: Mail, enabled: status.email_enabled },
  ];

  return (
    <PageContainer className="max-w-3xl">
      <div className="cb-overline text-accent">Notifications</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Stay in the loop</h1>

      <Card className="dashboard-card border-none">
        <CardContent className="p-6 space-y-4">
          {channels.map(c => (
            <div key={c.key} className="flex items-center justify-between p-4 hover:bg-secondary rounded-lg" data-testid={`notif-channel-${c.key}`}>
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                  <c.icon className="w-5 h-5 text-accent" />
                </div>
                <div>
                  <div className="font-display font-bold flex items-center gap-2">{c.label}
                    {c.enabled ?
                      <Badge className="bg-emerald-100 text-emerald-700 border-0 text-2xs font-bold flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> LIVE</Badge> :
                      <Badge className="bg-amber-100 text-amber-700 border-0 text-2xs font-bold flex items-center gap-1"><AlertCircle className="w-3 h-3" /> MOCK</Badge>
                    }
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">{c.desc}</div>
                </div>
              </div>
              <Switch checked={prefs[c.key]} onCheckedChange={(v) => setPrefs({...prefs, [c.key]: v})} data-testid={`notif-switch-${c.key}`} />
            </div>
          ))}
          <Button onClick={save} disabled={saving} className="bg-primary font-bold w-full" data-testid="notif-save-btn">Save preferences</Button>
        </CardContent>
      </Card>

      <Card className="mt-4 bg-secondary/50 border-none">
        <CardContent className="p-5 text-xs space-y-1 text-muted-foreground font-medium">
          <div className="font-bold uppercase tracking-widest text-foreground/70 mb-2">Wiring real notifications</div>
          <div>• Twilio: Add <code>TWILIO_ACCOUNT_SID</code>, <code>TWILIO_AUTH_TOKEN</code>, <code>TWILIO_PHONE_NUMBER</code>, <code>TWILIO_WHATSAPP_FROM</code> to <code>/app/backend/.env</code></div>
          <div>• SendGrid: Add <code>SENDGRID_API_KEY</code></div>
          <div>• WhatsApp templates must be pre-approved in Twilio Console (sandbox available immediately)</div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
