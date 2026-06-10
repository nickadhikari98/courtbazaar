import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Loader2, ShieldCheck } from "lucide-react";

export default function VendorOnboard() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);
  const [courts, setCourts] = useState([]);
  const [states, setStates] = useState([]);
  const [form, setForm] = useState({
    shop_name: "", owner_name: "", phone: "", address: "",
    court_ids: [], service_ids: [], pan: "", gst: "", aadhaar: "", bank_account: "", bank_ifsc: "",
  });
  const [stateId, setStateId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/services").then(r => setServices(r.data));
    api.get("/states").then(r => setStates(r.data));
  }, []);

  useEffect(() => {
    if (stateId) api.get("/courts", { params: { state_id: stateId } }).then(r => setCourts(r.data));
  }, [stateId]);

  const toggleCourt = (id) => setForm(f => ({...f, court_ids: f.court_ids.includes(id) ? f.court_ids.filter(x => x !== id) : [...f.court_ids, id]}));
  const toggleSvc = (id) => setForm(f => ({...f, service_ids: f.service_ids.includes(id) ? f.service_ids.filter(x => x !== id) : [...f.service_ids, id]}));

  const submit = async () => {
    if (!form.shop_name || !form.phone || form.court_ids.length === 0 || form.service_ids.length === 0) {
      toast.error("Please complete all required fields");
      return;
    }
    setLoading(true);
    try {
      await api.post("/vendors/onboard", form);
      toast.success("KYC submitted. We'll review within 24 hours.");
      navigate("/vendor");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Submission failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="p-6 lg:p-10 max-w-3xl mx-auto">
      <div className="cb-overline text-accent">Vendor onboarding</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Set up your shop on CourtBazaar</h1>

      <Card className="dashboard-card border-none">
        <CardContent className="p-6 space-y-5">
          <div>
            <div className="cb-overline mb-3">Shop details</div>
            <div className="space-y-3">
              <div><Label>Shop name *</Label><Input value={form.shop_name} onChange={(e) => setForm({...form, shop_name: e.target.value})} data-testid="ob-shop" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Owner name</Label><Input value={form.owner_name} onChange={(e) => setForm({...form, owner_name: e.target.value})} data-testid="ob-owner" /></div>
                <div><Label>Phone *</Label><Input value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value})} data-testid="ob-phone" /></div>
              </div>
              <div><Label>Address *</Label><Textarea value={form.address} onChange={(e) => setForm({...form, address: e.target.value})} data-testid="ob-address" /></div>
            </div>
          </div>

          <div>
            <div className="cb-overline mb-3">KYC details</div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>PAN</Label><Input value={form.pan} onChange={(e) => setForm({...form, pan: e.target.value})} placeholder="ABCDE1234F" data-testid="ob-pan" /></div>
              <div><Label>GST</Label><Input value={form.gst} onChange={(e) => setForm({...form, gst: e.target.value})} placeholder="22AAAAA0000A1Z5" data-testid="ob-gst" /></div>
              <div><Label>Aadhaar</Label><Input value={form.aadhaar} onChange={(e) => setForm({...form, aadhaar: e.target.value})} placeholder="XXXX XXXX XXXX" data-testid="ob-aadhaar" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div><Label>Bank Account</Label><Input value={form.bank_account} onChange={(e) => setForm({...form, bank_account: e.target.value})} data-testid="ob-bank" /></div>
              <div><Label>IFSC</Label><Input value={form.bank_ifsc} onChange={(e) => setForm({...form, bank_ifsc: e.target.value})} data-testid="ob-ifsc" /></div>
            </div>
          </div>

          <div>
            <div className="cb-overline mb-3">Courts you serve *</div>
            <select value={stateId} onChange={(e) => setStateId(e.target.value)} className="border border-border rounded-md h-10 px-3 text-sm bg-white w-full mb-3" data-testid="ob-state-select">
              <option value="">Select state</option>
              {states.map(s => <option key={s.state_id} value={s.state_id}>{s.name}</option>)}
            </select>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-60 overflow-y-auto p-1">
              {courts.map(c => (
                <label key={c.court_id} className="flex items-center gap-2 p-2 hover:bg-secondary rounded-lg cursor-pointer" data-testid={`ob-court-${c.court_id}`}>
                  <Checkbox checked={form.court_ids.includes(c.court_id)} onCheckedChange={() => toggleCourt(c.court_id)} />
                  <span className="text-sm font-semibold">{c.name}</span>
                </label>
              ))}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{form.court_ids.length} court(s) selected</div>
          </div>

          <div>
            <div className="cb-overline mb-3">Services you provide *</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto p-1">
              {services.map(s => (
                <label key={s.service_id} className="flex items-center gap-2 p-2 hover:bg-secondary rounded-lg cursor-pointer" data-testid={`ob-svc-${s.service_id}`}>
                  <Checkbox checked={form.service_ids.includes(s.service_id)} onCheckedChange={() => toggleSvc(s.service_id)} />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{s.name}</div>
                    <div className="text-xs text-muted-foreground">{s.category}</div>
                  </div>
                </label>
              ))}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{form.service_ids.length} service(s) selected</div>
          </div>

          <div className="bg-accent/5 border border-accent/30 rounded-xl p-4 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
            <div className="text-sm font-semibold">After submission, our team reviews your KYC within 24 hours.</div>
          </div>

          <Button onClick={submit} disabled={loading} className="bg-accent hover:bg-accent/90 w-full h-12 font-bold" data-testid="ob-submit-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            Submit for KYC review
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
