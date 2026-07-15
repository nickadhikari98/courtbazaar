import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Loader2, ShieldCheck } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function VendorOnboard() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);
  const [courts, setCourts] = useState([]);
  const [states, setStates] = useState([]);
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({
    shop_name: "", owner_name: "", phone: "", address: "",
    court_ids: [], service_ids: [], pan: "", gst: "", aadhaar: "", bank_account: "", bank_ifsc: "",
    vendor_category: "photocopy", has_gst: false, bio: "", hourly_rate: "",
  });
  const [stateId, setStateId] = useState("state_delhi");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/services").then(r => setServices(r.data));
    api.get("/states").then(r => setStates(r.data));
    api.get("/vendor-categories").then(r => setCategories(r.data));
  }, []);

  useEffect(() => {
    if (stateId) api.get("/courts", { params: { state_id: stateId } }).then(r => setCourts(r.data));
  }, [stateId]);

  const toggleCourt = (id) => setForm(f => ({...f, court_ids: f.court_ids.includes(id) ? f.court_ids.filter(x => x !== id) : [...f.court_ids, id]}));
  const toggleSvc = (id) => setForm(f => ({...f, service_ids: f.service_ids.includes(id) ? f.service_ids.filter(x => x !== id) : [...f.service_ids, id]}));

  const selectedCat = categories.find(c => c.id === form.vendor_category);
  const relevantServices = selectedCat?.service_categories?.length
    ? services.filter(s => selectedCat.service_categories.includes(s.category))
    : services;

  const submit = async () => {
    if (!form.shop_name || !form.phone || form.court_ids.length === 0 || form.service_ids.length === 0) {
      toast.error("Please complete shop name, phone, court(s) and at least one service");
      return;
    }
    if (form.has_gst && !form.gst) { toast.error("GST number required (or toggle off if you don't have GST)"); return; }
    setLoading(true);
    try {
      await api.post("/vendors/onboard", {
        ...form,
        hourly_rate: form.hourly_rate ? parseFloat(form.hourly_rate) : null,
        gst: form.has_gst ? form.gst : null,
      });
      toast.success("Submitted! KYC review in 24 hours.");
      navigate("/vendor");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Submission failed");
    } finally { setLoading(false); }
  };

  return (
    <PageContainer className="max-w-3xl">
      <div className="cb-overline text-accent">Vendor onboarding</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-2">List your business on CourtBazaar™</h1>
      <p className="text-muted-foreground font-medium mb-6">3-minute setup · GST optional · same 80/20 split for everyone</p>

      <Card className="dashboard-card border-none">
        <CardContent className="p-6 space-y-5">
          <div>
            <div className="cb-overline mb-3">1. Pick your category</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {categories.map(c => (
                <button key={c.id} onClick={() => setForm({...form, vendor_category: c.id, service_ids: []})}
                  className={`text-left p-3 rounded-xl border transition-all ${form.vendor_category === c.id ? 'border-accent bg-accent/10 shadow-sm' : 'border-border hover:border-foreground/30'}`}
                  data-testid={`cat-${c.id}`}>
                  <div className="font-display font-bold text-sm leading-tight">{c.name}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="cb-overline mb-3">2. Business details</div>
            <div className="space-y-3">
              <div><Label>Business / Shop name *</Label><Input value={form.shop_name} onChange={(e) => setForm({...form, shop_name: e.target.value})} data-testid="ob-shop" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Your name</Label><Input value={form.owner_name} onChange={(e) => setForm({...form, owner_name: e.target.value})} data-testid="ob-owner" /></div>
                <div><Label>Phone *</Label><Input value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value})} data-testid="ob-phone" /></div>
              </div>
              <div><Label>Address *</Label><Textarea value={form.address} onChange={(e) => setForm({...form, address: e.target.value})} data-testid="ob-address" rows={2} /></div>
              {(form.vendor_category === "stenographer" || form.vendor_category === "court_runner") && (
                <div><Label>Hourly rate (₹) — optional</Label><Input type="number" value={form.hourly_rate} onChange={(e) => setForm({...form, hourly_rate: e.target.value})} placeholder="800" data-testid="ob-rate" /></div>
              )}
              <div><Label>Short bio (optional)</Label><Textarea value={form.bio} onChange={(e) => setForm({...form, bio: e.target.value})} placeholder="Years of experience, languages, specialties" rows={2} data-testid="ob-bio" /></div>
            </div>
          </div>

          <div>
            <div className="cb-overline mb-3">3. GST & KYC</div>
            <div className="flex items-center justify-between p-4 bg-secondary rounded-lg mb-3">
              <div>
                <div className="font-display font-bold text-sm">I have a GST number</div>
                <div className="text-xs text-muted-foreground font-medium">Optional — non-GST vendors can onboard too</div>
              </div>
              <Switch checked={form.has_gst} onCheckedChange={(v) => setForm({...form, has_gst: v})} data-testid="ob-has-gst-switch" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              {form.has_gst && <div><Label>GST number *</Label><Input value={form.gst} onChange={(e) => setForm({...form, gst: e.target.value})} placeholder="07AAAAA0000A1Z5" data-testid="ob-gst" /></div>}
              <div><Label>PAN (optional)</Label><Input value={form.pan} onChange={(e) => setForm({...form, pan: e.target.value})} placeholder="ABCDE1234F" data-testid="ob-pan" /></div>
              <div><Label>Aadhaar (optional)</Label><Input value={form.aadhaar} onChange={(e) => setForm({...form, aadhaar: e.target.value})} placeholder="XXXX XXXX XXXX" data-testid="ob-aadhaar" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div><Label>Bank account (for payouts)</Label><Input value={form.bank_account} onChange={(e) => setForm({...form, bank_account: e.target.value})} data-testid="ob-bank" /></div>
              <div><Label>IFSC</Label><Input value={form.bank_ifsc} onChange={(e) => setForm({...form, bank_ifsc: e.target.value})} data-testid="ob-ifsc" /></div>
            </div>
          </div>

          <div>
            <div className="cb-overline mb-3">4. Courts you serve *</div>
            <select value={stateId} onChange={(e) => setStateId(e.target.value)} className="border border-border rounded-md h-10 px-3 text-sm bg-white w-full mb-3" data-testid="ob-state-select">
              {states.map(s => <option key={s.state_id} value={s.state_id}>{s.name}</option>)}
            </select>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-60 overflow-y-auto p-1">
              {courts.filter(c => c.serviceable !== false).map(c => (
                <label key={c.court_id} className="flex items-center gap-2 p-2 hover:bg-secondary rounded-lg cursor-pointer" data-testid={`ob-court-${c.court_id}`}>
                  <Checkbox checked={form.court_ids.includes(c.court_id)} onCheckedChange={() => toggleCourt(c.court_id)} />
                  <span className="text-sm font-semibold">{c.name}</span>
                </label>
              ))}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{form.court_ids.length} court(s) selected · only Delhi courts are serviceable currently</div>
          </div>

          <div>
            <div className="cb-overline mb-3">5. Services you offer * ({selectedCat?.name})</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto p-1">
              {relevantServices.map(s => (
                <label key={s.service_id} className="flex items-center gap-2 p-2 hover:bg-secondary rounded-lg cursor-pointer" data-testid={`ob-svc-${s.service_id}`}>
                  <Checkbox checked={form.service_ids.includes(s.service_id)} onCheckedChange={() => toggleSvc(s.service_id)} />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{s.name}</div>
                    <div className="text-xs text-muted-foreground">₹{s.base_price} {s.unit}</div>
                  </div>
                </label>
              ))}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{form.service_ids.length} service(s) selected</div>
          </div>

          <div className="bg-accent/5 border border-accent/30 rounded-xl p-4 text-sm space-y-1">
            <div className="font-display font-bold flex items-center gap-1.5"><ShieldCheck className="w-4 h-4 text-emerald-600" /> Revenue model (same for all categories)</div>
            <div className="text-xs text-muted-foreground font-medium">• You keep <b className="text-emerald-700">80%</b> of service price · platform retains 20% commission</div>
            <div className="text-xs text-muted-foreground font-medium">• Delivery fees are split <b>50:50</b> between you and the platform</div>
            <div className="text-xs text-muted-foreground font-medium">• Convenience fee goes to platform (covers payment + support)</div>
            <div className="text-xs text-muted-foreground font-medium">• Payouts processed automatically after order completion</div>
          </div>

          <Button onClick={submit} disabled={loading} className="bg-accent hover:bg-accent/90 w-full h-12 font-bold" data-testid="ob-submit-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            Submit for KYC review (24 hrs)
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
