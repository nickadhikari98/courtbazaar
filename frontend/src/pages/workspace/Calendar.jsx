import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Calendar as CalendarWidget } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { CalendarDays, Plus, Trash2, Package } from "lucide-react";

const toISODate = (d) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, local time

/* Real content for the Calendar workspace. Today this aggregates:
   - calendar_events (manual entries the user creates here)
   - court_holidays (a shared reference table — empty until seeded, also
     consumed by Availability's holiday-blocking in a later phase)
   - recent_orders, shown as a separate reference list (NOT plotted on the
     grid) — orders don't carry a real scheduled date today, so marking them
     "on" a calendar date would misrepresent what the data means.
   Hearings (Phase 5) and Matter-linked deadlines plug into this same view
   later without changing its shape. */
export default function Calendar() {
  const [data, setData] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("meeting");
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/calendar").then((r) => setData(r.data)).catch(() => setData({ events: [], holidays: [], recent_orders: [] }));
  useEffect(() => { load(); }, []);

  const markedDates = useMemo(() => {
    if (!data) return [];
    return [...data.events.map((e) => e.date), ...data.holidays.map((h) => h.date)].map((d) => new Date(d));
  }, [data]);

  const dayEvents = useMemo(() => {
    if (!data) return [];
    const iso = toISODate(selectedDate);
    return [
      ...data.events.filter((e) => e.date === iso).map((e) => ({ ...e, source: "event" })),
      ...data.holidays.filter((h) => h.date === iso).map((h) => ({ ...h, title: h.label, source: "holiday" })),
    ];
  }, [data, selectedDate]);

  const addEvent = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await api.post("/calendar/events", { title: title.trim(), date: toISODate(selectedDate), kind });
      setTitle("");
      toast.success("Added to calendar");
      load();
    } catch {
      toast.error("Could not add event");
    } finally {
      setSaving(false);
    }
  };

  const removeEvent = async (eventId) => {
    try {
      await api.delete(`/calendar/events/${eventId}`);
      load();
    } catch {
      toast.error("Could not remove event");
    }
  };

  return (
    <PageContainer className="max-w-5xl">
      <PageHeader
        eyebrow="Calendar"
        eyebrowIcon={CalendarDays}
        title="Your schedule, unified"
        description="Manual entries and court holidays today — hearings and deadlines will plug into this same view."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Card className="dashboard-card border-none">
          <CardContent className="p-4">
            <CalendarWidget
              mode="single"
              selected={selectedDate}
              onSelect={(d) => d && setSelectedDate(d)}
              modifiers={{ marked: markedDates }}
              modifiersClassNames={{ marked: "[&>button]:ring-2 [&>button]:ring-accent/50" }}
              className="mx-auto"
            />
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="dashboard-card border-none">
            <CardContent className="p-5">
              <div className="cb-overline text-accent mb-3">{selectedDate.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
              <div className="space-y-2 mb-4">
                {dayEvents.length === 0 && <p className="text-sm text-muted-foreground">Nothing scheduled.</p>}
                {dayEvents.map((e) => (
                  <div key={e.event_id || e.label} className="flex items-center justify-between gap-2 bg-secondary/50 rounded-lg px-3 py-2">
                    <div>
                      <div className="text-sm font-semibold">{e.title}</div>
                      <Badge variant="outline" className="text-2xs uppercase mt-0.5">{e.source === "holiday" ? "Court Holiday" : e.kind}</Badge>
                    </div>
                    {e.source === "event" && (
                      <button type="button" onClick={() => removeEvent(e.event_id)} className="text-muted-foreground hover:text-red-600">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a meeting or deadline" />
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="meeting">Meeting</SelectItem>
                    <SelectItem value="deadline">Deadline</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
                <Button type="button" onClick={addEvent} disabled={saving} className="bg-accent hover:bg-accent/90 font-bold flex-shrink-0">
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="dashboard-card border-none">
            <CardContent className="p-5">
              <div className="cb-overline mb-3 flex items-center gap-1.5"><Package className="w-3.5 h-3.5" /> Recent orders</div>
              <div className="space-y-1.5">
                {(data?.recent_orders || []).slice(0, 5).map((o) => (
                  <div key={o.order_id} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs text-muted-foreground">{o.order_id}</span>
                    <span className="truncate">{o.court_name}</span>
                    <Badge variant="outline" className="text-2xs uppercase">{o.status}</Badge>
                  </div>
                ))}
                {data && data.recent_orders.length === 0 && <p className="text-sm text-muted-foreground">No orders yet.</p>}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
