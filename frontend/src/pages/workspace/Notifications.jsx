import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Bell, BellRing } from "lucide-react";
import { NotificationPrefsCard } from "@/pages/customer/NotificationPrefs";
import EmptyState from "@/components/shared/EmptyState";
import Loading from "@/components/shared/Loading";

/* Notification Center — the global feed every event across hearings,
   services, payments, documents, AI, and support fans into (see
   notifications.record_notification_event, called alongside notify() at
   each event's existing dispatch site). Settings (channel toggles) moves
   here as a tab instead of its own sidebar entry. */
export default function Notifications() {
  const [items, setItems] = useState(null);

  const load = () => api.get("/notifications").then((r) => setItems(r.data || []));
  useEffect(() => { load(); }, []);

  const markRead = async (id) => {
    await api.put(`/notifications/${id}/read`);
    setItems((prev) => prev.map((n) => n.notification_id === id ? { ...n, read_at: new Date().toISOString() } : n));
  };

  return (
    <PageContainer className="max-w-3xl">
      <PageHeader eyebrow="Notifications" eyebrowIcon={Bell} title="Notification Center" />

      <Tabs defaultValue="feed" className="mt-6">
        <TabsList>
          <TabsTrigger value="feed">Feed</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="feed" className="mt-4 space-y-2">
          {items === null && <Loading />}
          {items?.length === 0 && <EmptyState icon={Bell} description="You're all caught up." />}
          {items?.map((n) => (
            <Card
              key={n.notification_id}
              className={`border-none cursor-pointer transition-shadow ${n.read_at ? "bg-white" : "bg-accent/5 hover:shadow-md"}`}
              onClick={() => !n.read_at && markRead(n.notification_id)}
            >
              <CardContent className="p-4 flex items-start gap-3">
                {n.read_at ? <Bell className="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" /> : <BellRing className="w-4 h-4 text-accent mt-0.5 flex-shrink-0" />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-display font-bold text-sm">{n.title}</span>
                    {!n.read_at && <Badge className="bg-accent text-white border-0 text-2xs h-4 px-1.5">NEW</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">{n.body}</p>
                  <span className="text-2xs text-muted-foreground/70 font-semibold uppercase tracking-wide">
                    {new Date(n.created_at).toLocaleString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <NotificationPrefsCard />
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
