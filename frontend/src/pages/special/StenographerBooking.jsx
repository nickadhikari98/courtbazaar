import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Mic, Clock, Star, ShieldCheck, Loader2 } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function StenographerBooking() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);
  const [states, setStates] = useState([]);
  const [courts, setCourts] = useState([]);
  const [stenos, setStenos] = useState([]);
  const [form, setForm] = useState({
    service_id: "", state_id: "state_delhi", court_id: "",
    date: new Date().toISOString().slice(0,10),
    start_time: "10:00", hours: 2,
    delivery_option: "court", delivery_address: "", notes: "",
    stenographer_id: "",
  });
  const [pricing, setPricing] = useState(null);
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    api.get("/services", { params: { category: "Stenographer Services" } }).then(r => {
      setServices(r.data);
      if (r.data.length && !form.service_id) setForm(f => ({...f, service_id: r.data[0].service_id}));
    });
    api.get("/states").then(r => setStates(r.data));
  }, []);

  useEffect(() => {
    if (form.state_id) api.get("/courts", { params: { state_id: form.state_id } }).then(r => setCourts(r.data));
  }, [form.state_id]);

  useEffect(() => {
    if (form.court_id) api.get("/stenographers", { params: { court_id: form.court_id } }).then(r => setStenos(r.data));
  }, [form.court_id]);

  // Live price
  useEffect(() => {
    if (form.service_id && form.court_id && form.hours > 0) {
      api.post("/orders/quote", {
        services: [{ service_id: form.service_id, qty: form.hours }],
        state_id: form.state_id, court_id: form.court_id,
        delivery_option: form.delivery_option, urgent: false, file_ids: [],
      }).then(r => setPricing(r.data)).catch(() => setPricing(null));
    }
  }, [form.service_id, form.court_id, form.hours, form.delivery_option]);

  const svc = services.find(s => s.service_id === form.service_id);
  const minHours = svc?.min_hours || 1;

  const submit = async () => {
    if (!form.court_id) { toast.error("Pick a court"); return; }
    if (form.hours < minHours) { toast.error(`Minimum ${minHours} hour(s)`); return; }
    setBooking(true);
    try {
      const { data } = await api.post("/stenographers/book", form);
      toast.success(`Booked: ${data.order_id}`);
      navigate(`/orders/${data.order_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Booking failed"); }
    finally { setBooking(false); }
  };

  return (
    <PageContainer className="max-w-5xl">
      <div className="cb-overline text-accent flex items-center gap-1.5"><Mic className="w-3 h-3" /> Stenographer services</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Book a stenographer · hourly</h1>
      <p className="text-muted-foreground font-medium mt-1">Court hearings, depositions, transcriptions, dictations — verified, on-demand.</p>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-4">
          <Card className="dashboard-card border-none"><CardContent className="p-5 space-y-4">
            <div>
              <Label>Service type</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                {services.map(s => (
                  <button key={s.service_id} onClick={() => setForm({...form, service_id: s.service_id, hours: Math.max(s.min_hours || 1, form.hours)})}
                    className={`text-left p-3 rounded-xl border transition-all ${form.service_id === s.service_id ? 'border-accent bg-accent/5 shadow-sm' : 'border-border hover:border-foreground/30'}`}
                    data-testid={`steno-svc-${s.service_id}`}>
                    <div className="font-display font-bold text-sm">{s.name.replace(/^Stenographer\s*[—-]\s*/, '')}</div>
                    <div className="text-xs text-muted-foreground font-semibold mt-1">{formatINR(s.base_price)}/hr · min {s.min_hours}h</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div><Label>State</Label>
                <Select value={form.state_id} onValueChange={(v) => setForm({...form, state_id: v, court_id: ""})}>
                  <SelectTrigger data-testid="steno-state"><SelectValue /></SelectTrigger>
                  <SelectContent>{states.map(s => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Court</Label>
                <Select value={form.court_id} onValueChange={(v) => setForm({...form, court_id: v})}>
                  <SelectTrigger data-testid="steno-court"><SelectValue placeholder="Pick court" /></SelectTrigger>
                  <SelectContent>{courts.map(c => <SelectItem key={c.court_id} value={c.court_id} disabled={c.serviceable === false}>{c.name}{c.serviceable === false ? ' (Coming soon)' : ''}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div><Label>Date</Label><Input type="date" value={form.date} onChange={(e) => setForm({...form, date: e.target.value})} min={new Date().toISOString().slice(0,10)} data-testid="steno-date" /></div>
              <div><Label>Start time</Label><Input type="time" value={form.start_time} onChange={(e) => setForm({...form, start_time: e.target.value})} data-testid="steno-time" /></div>
              <div><Label>Hours (min {minHours})</Label><Input type="number" min={minHours} max={12} value={form.hours} onChange={(e) => setForm({...form, hours: parseInt(e.target.value) || minHours})} data-testid="steno-hours" /></div>
            </div>

            <div><Label>Notes (case details, hearing reference, etc.)</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})} placeholder="e.g. WP 1234/2026, hearing before HMJ Sharma" data-testid="steno-notes" />
            </div>

            {stenos.length > 0 && (
              <div>
                <Label>Pick specific stenographer (optional)</Label>
                <Select value={form.stenographer_id || "auto"} onValueChange={(v) => setForm({...form, stenographer_id: v === "auto" ? "" : v})}>
                  <SelectTrigger data-testid="steno-pick"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-match (recommended)</SelectItem>
                    {stenos.map(s => <SelectItem key={s.vendor_id} value={s.vendor_id}>{s.shop_name} ★ {s.rating?.toFixed(1) || '—'}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
          </CardContent></Card>
        </div>

        <div className="space-y-4">
          <Card className="dashboard-card border-none"><CardContent className="p-5">
            <div className="cb-overline text-accent">Quote</div>
            {pricing ? (
              <div className="mt-3 space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">{form.hours} hrs × {formatINR(svc?.base_price || 0)}</span><span className="font-bold">{formatINR(pricing.subtotal)}</span></div>
                {pricing.delivery_fee > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Delivery</span><span className="font-bold">{formatINR(pricing.delivery_fee)}</span></div>}
                <div className="flex justify-between"><span className="text-muted-foreground">Convenience</span><span className="font-bold">{formatINR(pricing.convenience_fee)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">GST 18%</span><span className="font-bold">{formatINR(pricing.gst)}</span></div>
                <div className="cb-divider my-2"></div>
                <div className="flex justify-between items-baseline"><span className="font-display font-bold">Total</span><span className="font-display font-black text-2xl text-accent">{formatINR(pricing.total)}</span></div>
              </div>
            ) : <div className="text-sm text-muted-foreground mt-3">Pick service + court to see price</div>}
            <Button onClick={submit} disabled={booking || !pricing} className="mt-5 bg-accent hover:bg-accent/90 font-bold w-full h-12" data-testid="steno-book-btn">
              {booking ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Book stenographer
            </Button>
          </CardContent></Card>

          <Card className="bg-accent/5 border-accent/30"><CardContent className="p-4 text-xs space-y-1">
            <div className="flex items-center gap-1.5 font-bold"><ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> KYC-verified stenographers</div>
            <div className="flex items-center gap-1.5 font-bold"><Clock className="w-3.5 h-3.5 text-accent" /> Hourly slots · pay per hour</div>
            <div className="flex items-center gap-1.5 font-bold"><Star className="w-3.5 h-3.5 text-accent" /> Rated by advocates after hearing</div>
          </CardContent></Card>
        </div>
      </div>
    </PageContainer>
  );
}
