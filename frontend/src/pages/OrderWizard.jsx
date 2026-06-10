import React, { useEffect, useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import {
  Upload, Check, ChevronRight, ChevronLeft, FileText, X, Loader2, MapPin,
  Truck, Home, Building2, Cloud, Zap, ShieldCheck
} from "lucide-react";
import * as Icons from "lucide-react";

const STEPS = ["Upload", "Services", "Court", "Delivery", "Review"];

export default function OrderWizard() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const preselectService = params.get("service");
  const [step, setStep] = useState(0);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [services, setServices] = useState([]);
  const [selectedServices, setSelectedServices] = useState({});
  const [states, setStates] = useState([]);
  const [courts, setCourts] = useState([]);
  const [stateId, setStateId] = useState("");
  const [courtId, setCourtId] = useState("");
  const [delivery, setDelivery] = useState("chamber");
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [urgent, setUrgent] = useState(false);
  const [notes, setNotes] = useState("");
  const [pricing, setPricing] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.get("/services").then(r => {
      setServices(r.data);
      if (preselectService) setSelectedServices({ [preselectService]: 1 });
    });
    api.get("/states").then(r => setStates(r.data));
  }, []);

  useEffect(() => {
    if (stateId) api.get("/courts", { params: { state_id: stateId } }).then(r => setCourts(r.data));
    else setCourts([]);
  }, [stateId]);

  const handleFileSelect = async (e) => {
    const fileList = Array.from(e.target.files || []);
    if (!fileList.length) return;
    setUploading(true);
    try {
      for (const f of fileList) {
        const fd = new FormData();
        fd.append("file", f);
        const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setFiles((prev) => [...prev, data]);
      }
      toast.success(`Uploaded ${fileList.length} file(s)`);
    } catch (err) {
      toast.error("Upload failed");
    } finally { setUploading(false); }
  };

  const removeFile = (id) => setFiles(files.filter(f => f.file_id !== id));

  const toggleService = (id) => {
    setSelectedServices((p) => {
      const n = { ...p };
      if (n[id]) delete n[id]; else n[id] = 1;
      return n;
    });
  };
  const setQty = (id, qty) => setSelectedServices((p) => ({ ...p, [id]: Math.max(1, parseInt(qty) || 1) }));

  const categoryGroups = useMemo(() => {
    const g = {};
    for (const s of services) {
      g[s.category] = g[s.category] || [];
      g[s.category].push(s);
    }
    return g;
  }, [services]);

  const totalSelectedItems = Object.values(selectedServices).reduce((a,b) => a + b, 0);

  const fetchQuote = async () => {
    const svcList = Object.entries(selectedServices).map(([service_id, qty]) => ({ service_id, qty }));
    if (!svcList.length || !courtId) return;
    try {
      const { data } = await api.post("/orders/quote", {
        services: svcList, state_id: stateId, court_id: courtId,
        delivery_option: delivery, urgent, file_ids: files.map(f => f.file_id),
      });
      setPricing(data);
    } catch (e) { /* ignore */ }
  };

  useEffect(() => {
    if (step === 4 && courtId && totalSelectedItems > 0) fetchQuote();
  }, [step, urgent, delivery, courtId]);

  const placeOrder = async () => {
    setCreating(true);
    try {
      const svcList = Object.entries(selectedServices).map(([service_id, qty]) => ({ service_id, qty }));
      const { data } = await api.post("/orders", {
        services: svcList, state_id: stateId, court_id: courtId,
        delivery_option: delivery, delivery_address: deliveryAddress,
        file_ids: files.map(f => f.file_id), urgent, notes,
      });
      toast.success(`Order placed: ${data.order_id}`);
      navigate(`/orders/${data.order_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to place order");
    } finally { setCreating(false); }
  };

  const canNext = () => {
    if (step === 0) return files.length > 0 || totalSelectedItems > 0; // allow skip files for some flows
    if (step === 1) return totalSelectedItems > 0;
    if (step === 2) return !!courtId;
    if (step === 3) return delivery !== "chamber" || deliveryAddress.length > 5 || delivery !== "chamber";
    return true;
  };

  const deliveryOptions = [
    { id: "pickup", label: "Vendor Pickup", desc: "Pick up from vendor shop", icon: MapPin, fee: 0 },
    { id: "chamber", label: "Chamber Delivery", desc: "Deliver to your chamber", icon: Home, fee: 79 },
    { id: "court", label: "Court Delivery", desc: "Hand over inside court premises", icon: Building2, fee: 49 },
    { id: "digital", label: "Digital Delivery", desc: "Email / portal upload", icon: Cloud, fee: 0 },
  ];

  return (
    <div className="p-6 lg:p-10 max-w-5xl mx-auto">
      <div className="mb-8">
        <div className="cb-overline text-accent">Smart order wizard</div>
        <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1">Place a new order</h1>
        <div className="mt-5">
          <Progress value={(step / (STEPS.length - 1)) * 100} className="h-1.5" />
          <div className="mt-3 flex justify-between text-xs font-bold">
            {STEPS.map((s, i) => (
              <div key={s} className={`flex items-center gap-1.5 ${i <= step ? 'text-foreground' : 'text-muted-foreground'}`} data-testid={`step-indicator-${i}`}>
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${i < step ? 'bg-accent text-white' : i === step ? 'bg-primary text-white' : 'bg-secondary'}`}>
                  {i < step ? <Check className="w-3 h-3" /> : i + 1}
                </div>
                <span className="hidden sm:inline">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <Card className="dashboard-card border-none">
        <CardContent className="p-6 lg:p-8">
          {/* Step 0: Upload */}
          {step === 0 && (
            <div className="space-y-4" data-testid="wizard-step-upload">
              <h2 className="font-display font-bold text-2xl tracking-tight">Upload your documents</h2>
              <p className="text-muted-foreground font-medium">PDFs, images, or scans. We'll handle the rest.</p>
              <label className="block border-2 border-dashed border-border rounded-2xl p-10 text-center cursor-pointer hover:border-accent hover:bg-accent/5 transition-colors" data-testid="wizard-file-dropzone">
                <input type="file" multiple className="hidden" onChange={handleFileSelect} accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" />
                <Upload className="w-10 h-10 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
                <div className="font-display font-bold text-lg">{uploading ? "Uploading…" : "Drop files or tap to upload"}</div>
                <div className="text-xs text-muted-foreground mt-1 font-semibold">PDF, JPG, PNG, DOCX up to 25 MB</div>
              </label>
              {files.length > 0 && (
                <div className="space-y-2 pt-2">
                  {files.map(f => (
                    <div key={f.file_id} className="flex items-center justify-between bg-secondary rounded-lg p-3" data-testid={`uploaded-file-${f.file_id}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText className="w-5 h-5 text-accent shrink-0" />
                        <div className="min-w-0">
                          <div className="font-semibold text-sm truncate">{f.original_filename}</div>
                          <div className="text-xs text-muted-foreground">{(f.size / 1024).toFixed(1)} KB</div>
                        </div>
                      </div>
                      <button onClick={() => removeFile(f.file_id)} className="p-1 hover:bg-white rounded" data-testid={`remove-file-${f.file_id}`}>
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="text-xs text-muted-foreground italic">You can skip this step if your services don't require document upload.</div>
            </div>
          )}

          {/* Step 1: Services */}
          {step === 1 && (
            <div className="space-y-6" data-testid="wizard-step-services">
              <div>
                <h2 className="font-display font-bold text-2xl tracking-tight">Select services</h2>
                <p className="text-muted-foreground font-medium">{totalSelectedItems} item{totalSelectedItems !== 1 ? 's' : ''} selected</p>
              </div>
              {Object.entries(categoryGroups).map(([cat, list]) => (
                <div key={cat}>
                  <div className="cb-overline mb-3 text-accent">{cat}</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {list.map((s) => {
                      const Icon = Icons[s.icon] || FileText;
                      const selected = !!selectedServices[s.service_id];
                      return (
                        <div key={s.service_id} className={`border rounded-xl p-4 cursor-pointer transition-all ${selected ? 'border-accent bg-accent/5 shadow-sm' : 'border-border hover:border-foreground/30'}`} onClick={() => !selected && toggleService(s.service_id)} data-testid={`service-card-${s.service_id}`}>
                          <div className="flex items-start gap-3">
                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${selected ? 'bg-accent text-white' : 'bg-secondary text-foreground'}`}>
                              <Icon className="w-5 h-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="font-display font-bold text-sm leading-tight">{s.name}</div>
                              <div className="text-xs text-muted-foreground font-semibold mt-0.5">{formatINR(s.base_price)} {s.unit}</div>
                              {selected && (
                                <div className="flex items-center gap-2 mt-3" onClick={(e) => e.stopPropagation()}>
                                  <Input type="number" min="1" value={selectedServices[s.service_id]} onChange={(e) => setQty(s.service_id, e.target.value)} className="w-20 h-8 text-sm" data-testid={`qty-${s.service_id}`} />
                                  <button onClick={() => toggleService(s.service_id)} className="text-xs font-bold text-destructive hover:underline" data-testid={`remove-svc-${s.service_id}`}>Remove</button>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Step 2: Court */}
          {step === 2 && (
            <div className="space-y-5" data-testid="wizard-step-court">
              <div>
                <h2 className="font-display font-bold text-2xl tracking-tight">Destination court</h2>
                <p className="text-muted-foreground font-medium">Where should the work be completed?</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label>State / UT</Label>
                  <Select value={stateId} onValueChange={(v) => { setStateId(v); setCourtId(""); }}>
                    <SelectTrigger data-testid="state-select"><SelectValue placeholder="Select state" /></SelectTrigger>
                    <SelectContent>
                      {states.map(s => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Court</Label>
                  <Select value={courtId} onValueChange={setCourtId} disabled={!stateId}>
                    <SelectTrigger data-testid="court-select"><SelectValue placeholder={stateId ? "Select court" : "Choose state first"} /></SelectTrigger>
                    <SelectContent>
                      {courts.map(c => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {courtId && (
                <Card className="bg-accent/5 border-accent/30">
                  <CardContent className="p-4 flex items-center gap-3">
                    <ShieldCheck className="w-5 h-5 text-emerald-600" />
                    <div className="text-sm font-semibold">Verified vendors available at this court. Auto-matching enabled.</div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Step 3: Delivery */}
          {step === 3 && (
            <div className="space-y-5" data-testid="wizard-step-delivery">
              <h2 className="font-display font-bold text-2xl tracking-tight">Delivery preference</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {deliveryOptions.map(opt => (
                  <div key={opt.id} onClick={() => setDelivery(opt.id)} className={`border rounded-xl p-4 cursor-pointer transition-all ${delivery === opt.id ? 'border-accent bg-accent/5 shadow-sm' : 'border-border hover:border-foreground/30'}`} data-testid={`delivery-opt-${opt.id}`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${delivery === opt.id ? 'bg-accent text-white' : 'bg-secondary text-foreground'}`}>
                        <opt.icon className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="font-display font-bold text-sm">{opt.label}</div>
                        <div className="text-xs text-muted-foreground font-medium mt-0.5">{opt.desc}</div>
                        <div className="text-xs font-bold mt-1.5">{opt.fee === 0 ? 'Free' : `+${formatINR(opt.fee)}`}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {delivery === "chamber" && (
                <div>
                  <Label>Chamber address</Label>
                  <Textarea value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} placeholder="Chamber no., court complex, city" data-testid="delivery-address-input" />
                </div>
              )}
              <div className="flex items-center justify-between bg-secondary rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <Zap className="w-5 h-5 text-accent" />
                  <div>
                    <div className="font-bold text-sm">Urgent order (25% surcharge)</div>
                    <div className="text-xs text-muted-foreground">Same-day priority</div>
                  </div>
                </div>
                <Switch checked={urgent} onCheckedChange={setUrgent} data-testid="urgent-switch" />
              </div>
              <div>
                <Label>Special instructions (optional)</Label>
                <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Punching holes, double-sided, specific colour, etc." data-testid="notes-input" />
              </div>
            </div>
          )}

          {/* Step 4: Review */}
          {step === 4 && (
            <div className="space-y-5" data-testid="wizard-step-review">
              <h2 className="font-display font-bold text-2xl tracking-tight">Review & pay</h2>
              {pricing ? (
                <>
                  <div className="space-y-2">
                    {pricing.breakdown.map((b, i) => (
                      <div key={i} className="flex items-center justify-between text-sm py-1.5 border-b border-border">
                        <span className="font-medium">{b.name} × {b.qty}</span>
                        <span className="font-bold">{formatINR(b.line_total)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-semibold">{formatINR(pricing.subtotal)}</span></div>
                    {pricing.delivery_fee > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Delivery</span><span className="font-semibold">{formatINR(pricing.delivery_fee)}</span></div>}
                    {pricing.urgent_fee > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Urgent surcharge</span><span className="font-semibold">{formatINR(pricing.urgent_fee)}</span></div>}
                    <div className="flex justify-between"><span className="text-muted-foreground">Convenience fee</span><span className="font-semibold">{formatINR(pricing.convenience_fee)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">GST (18%)</span><span className="font-semibold">{formatINR(pricing.gst)}</span></div>
                  </div>
                  <div className="cb-divider"></div>
                  <div className="flex justify-between items-baseline">
                    <span className="font-display font-bold text-xl">Total</span>
                    <span className="font-display font-black text-3xl text-accent tracking-tight">{formatINR(pricing.total)}</span>
                  </div>
                  <div className="bg-secondary rounded-xl p-4 text-xs space-y-1">
                    <div><span className="cb-overline">Destination</span> &nbsp; <span className="font-bold">{courts.find(c => c.court_id === courtId)?.name}</span></div>
                    <div><span className="cb-overline">Delivery</span> &nbsp; <span className="font-bold capitalize">{delivery}</span></div>
                    <div><span className="cb-overline">Files</span> &nbsp; <span className="font-bold">{files.length} attached</span></div>
                  </div>
                </>
              ) : (
                <div className="h-40 flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-accent" /></div>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="flex justify-between mt-8 pt-6 border-t border-border">
            <Button variant="outline" onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0} className="font-bold" data-testid="wizard-back-btn">
              <ChevronLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            {step < 4 ? (
              <Button onClick={() => setStep(s => s + 1)} disabled={!canNext()} className="bg-primary hover:bg-primary/90 font-bold" data-testid="wizard-next-btn">
                Continue <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button onClick={placeOrder} disabled={creating || !pricing} className="bg-accent hover:bg-accent/90 font-bold" data-testid="wizard-place-order-btn">
                {creating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                Place Order — {pricing ? formatINR(pricing.total) : "Loading…"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
