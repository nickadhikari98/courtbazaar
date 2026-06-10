import React, { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  CheckCircle2, Clock, Loader2, Truck, Package, FileText, Star,
  MapPin, ShieldCheck, Receipt, Download, AlertCircle, ArrowLeft
} from "lucide-react";

const STATUS_FLOW = [
  { key: "placed", label: "Order Placed" },
  { key: "matched", label: "Vendor Matched" },
  { key: "accepted", label: "Vendor Accepted" },
  { key: "processing", label: "In Production" },
  { key: "quality_check", label: "Quality Check" },
  { key: "ready", label: "Ready" },
  { key: "out_for_delivery", label: "Out for Delivery" },
  { key: "delivered", label: "Delivered" },
  { key: "completed", label: "Completed" },
];

export default function OrderDetail() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [rateOpen, setRateOpen] = useState(false);
  const [rating, setRating] = useState(5);
  const [review, setReview] = useState("");
  const [statusPolling, setStatusPolling] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/orders/${orderId}`);
    setOrder(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, [orderId]);

  // Payment polling after Stripe return
  useEffect(() => {
    if (!sessionId) return;
    setStatusPolling(true);
    let attempts = 0;
    const poll = async () => {
      attempts++;
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          toast.success("Payment successful!");
          setStatusPolling(false);
          await load();
          return;
        }
        if (data.status === "expired") {
          toast.error("Payment session expired.");
          setStatusPolling(false);
          return;
        }
        if (attempts < 8) setTimeout(poll, 2500);
        else setStatusPolling(false);
      } catch (e) { setStatusPolling(false); }
    };
    poll();
  }, [sessionId]);

  const pay = async () => {
    setPaying(true);
    try {
      const { data } = await api.post("/payments/checkout", {
        order_id: orderId,
        origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (e) {
      toast.error("Could not start payment");
      setPaying(false);
    }
  };

  const updateStatus = async (status) => {
    try {
      await api.post(`/orders/${orderId}/status`, { status });
      toast.success(`Marked ${status.replace(/_/g, ' ')}`);
      load();
    } catch { toast.error("Update failed"); }
  };

  const submitRating = async () => {
    try {
      await api.post(`/orders/${orderId}/rate`, { order_id: orderId, rating, review });
      toast.success("Thanks for your review!");
      setRateOpen(false);
      load();
    } catch { toast.error("Could not submit review"); }
  };

  if (loading) return <div className="p-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-accent" /></div>;
  if (!order) return <div className="p-10 text-center">Order not found</div>;

  const currentStepIdx = STATUS_FLOW.findIndex(s => s.key === order.status);

  return (
    <div className="p-6 lg:p-10 max-w-5xl mx-auto">
      <button onClick={() => navigate(-1)} className="text-sm font-semibold text-muted-foreground hover:text-foreground mb-4 flex items-center gap-1.5" data-testid="back-btn">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <div className="cb-overline text-accent">Order detail</div>
          <h1 className="font-display font-black text-3xl mt-1 tracking-tighter font-mono">{order.order_id}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge className={`${order.payment_status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'} border-0 font-bold`} data-testid="order-payment-status">
              {order.payment_status === 'paid' ? 'PAID' : 'PAYMENT PENDING'}
            </Badge>
            <Badge className="bg-primary text-white border-0 font-bold uppercase text-[10px]" data-testid="order-status-badge">{order.status.replace(/_/g, ' ')}</Badge>
            {order.urgent && <Badge className="bg-destructive text-white border-0 font-bold uppercase text-[10px]">URGENT</Badge>}
          </div>
        </div>
        <div className="text-right">
          <div className="cb-overline">Total</div>
          <div className="font-display font-black text-3xl text-accent tracking-tight">{formatINR(order.pricing?.total)}</div>
        </div>
      </div>

      {statusPolling && (
        <Card className="mb-6 bg-amber-50 border-amber-200">
          <CardContent className="p-4 flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-amber-700" />
            <div className="text-sm font-semibold">Verifying payment status…</div>
          </CardContent>
        </Card>
      )}

      {order.payment_status !== "paid" && user?.role === "advocate" && (
        <Card className="mb-6 border-accent bg-accent/5">
          <CardContent className="p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <div className="font-display font-bold text-lg">Complete payment to start your order</div>
              <div className="text-sm text-muted-foreground font-medium">Secure checkout via Stripe (test mode)</div>
            </div>
            <Button onClick={pay} disabled={paying} className="bg-accent hover:bg-accent/90 font-bold h-12 px-6" data-testid="pay-now-btn">
              {paying ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Pay {formatINR(order.pricing.total)}
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Timeline */}
        <div className="lg:col-span-2">
          <Card className="dashboard-card border-none">
            <CardContent className="p-6">
              <h3 className="font-display font-bold text-lg tracking-tight mb-5">Live tracking</h3>
              <div className="space-y-0">
                {STATUS_FLOW.map((s, i) => {
                  const completed = i <= currentStepIdx;
                  const active = i === currentStepIdx;
                  return (
                    <div key={s.key} className="flex gap-4" data-testid={`timeline-${s.key}`}>
                      <div className="flex flex-col items-center">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${completed ? 'bg-accent text-white' : 'bg-secondary text-muted-foreground'}`}>
                          {completed ? <CheckCircle2 className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                          {active && <div className="absolute w-8 h-8 rounded-full bg-accent/30 live-dot"></div>}
                        </div>
                        {i < STATUS_FLOW.length - 1 && <div className={`w-0.5 h-10 ${completed ? 'bg-accent' : 'bg-border'}`}></div>}
                      </div>
                      <div className="pb-6 flex-1">
                        <div className={`font-display font-bold text-sm ${completed ? 'text-foreground' : 'text-muted-foreground'}`}>{s.label}</div>
                        {(order.timeline || []).filter(t => t.status === s.key).map((t, j) => (
                          <div key={j} className="text-xs text-muted-foreground font-medium mt-0.5">{new Date(t.at).toLocaleString('en-IN')}</div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Vendor action buttons */}
              {user?.role === "vendor" && order.vendor_id === user.user_id && currentStepIdx < STATUS_FLOW.length - 2 && (
                <div className="mt-4 pt-4 border-t border-border flex flex-wrap gap-2">
                  {STATUS_FLOW.slice(currentStepIdx + 1, currentStepIdx + 3).map(s => (
                    <Button key={s.key} onClick={() => updateStatus(s.key)} variant="outline" className="font-bold" data-testid={`vendor-action-${s.key}`}>
                      Mark {s.label} →
                    </Button>
                  ))}
                </div>
              )}

              {/* Customer completion */}
              {user?.role === "advocate" && order.status === "delivered" && !order.rating && (
                <div className="mt-4 pt-4 border-t border-border flex gap-2">
                  <Button onClick={() => updateStatus("completed")} className="bg-primary font-bold" data-testid="confirm-completion-btn">
                    Confirm Receipt
                  </Button>
                  <Button onClick={() => setRateOpen(true)} variant="outline" className="font-bold" data-testid="rate-btn">
                    <Star className="w-4 h-4 mr-1.5" /> Rate
                  </Button>
                </div>
              )}
              {order.rating && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="cb-overline">Your rating</div>
                  <div className="flex gap-0.5 mt-1">{[1,2,3,4,5].map(i => <Star key={i} className={`w-4 h-4 ${i <= order.rating ? 'text-accent fill-accent' : 'text-muted'}`} />)}</div>
                  {order.review && <div className="text-sm text-muted-foreground mt-1 font-medium">{order.review}</div>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right rail */}
        <div className="space-y-4">
          <Card className="dashboard-card border-none">
            <CardContent className="p-5">
              <div className="cb-overline">Destination court</div>
              <div className="font-display font-bold text-base mt-1">{order.court_name}</div>
              <div className="text-xs text-muted-foreground font-semibold">{order.state_name}</div>
              {order.vendor_name && (
                <>
                  <div className="cb-divider my-3"></div>
                  <div className="cb-overline">Assigned vendor</div>
                  <div className="font-display font-bold text-base mt-1 flex items-center gap-2">
                    {order.vendor_name}
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  </div>
                </>
              )}
              <div className="cb-divider my-3"></div>
              <div className="cb-overline">Delivery</div>
              <div className="font-semibold text-sm capitalize mt-1 flex items-center gap-1.5">
                <Truck className="w-4 h-4 text-accent" />
                {order.delivery_option} delivery
              </div>
              {order.delivery_address && <div className="text-xs text-muted-foreground mt-1">{order.delivery_address}</div>}
            </CardContent>
          </Card>

          <Card className="dashboard-card border-none">
            <CardContent className="p-5">
              <div className="cb-overline">Invoice</div>
              <div className="space-y-1 text-sm mt-2">
                {order.pricing?.breakdown?.map((b, i) => (
                  <div key={i} className="flex justify-between"><span className="text-muted-foreground">{b.name} × {b.qty}</span><span className="font-semibold">{formatINR(b.line_total)}</span></div>
                ))}
                <div className="cb-divider my-2"></div>
                {order.pricing?.delivery_fee > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Delivery</span><span className="font-semibold">{formatINR(order.pricing.delivery_fee)}</span></div>}
                {order.pricing?.urgent_fee > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Urgent</span><span className="font-semibold">{formatINR(order.pricing.urgent_fee)}</span></div>}
                <div className="flex justify-between"><span className="text-muted-foreground">Conv. fee</span><span className="font-semibold">{formatINR(order.pricing?.convenience_fee)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">GST</span><span className="font-semibold">{formatINR(order.pricing?.gst)}</span></div>
                <div className="cb-divider my-2"></div>
                <div className="flex justify-between font-display font-bold text-base"><span>Total</span><span>{formatINR(order.pricing?.total)}</span></div>
              </div>
            </CardContent>
          </Card>

          {order.file_ids?.length > 0 && (
            <Card className="dashboard-card border-none">
              <CardContent className="p-5">
                <div className="cb-overline mb-2">Attached files</div>
                <div className="text-sm font-semibold flex items-center gap-2">
                  <FileText className="w-4 h-4 text-accent" /> {order.file_ids.length} file(s)
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <Dialog open={rateOpen} onOpenChange={setRateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Rate this order</DialogTitle></DialogHeader>
          <div className="flex justify-center gap-1 my-4">
            {[1,2,3,4,5].map(i => (
              <button key={i} onClick={() => setRating(i)} data-testid={`star-${i}`}>
                <Star className={`w-8 h-8 ${i <= rating ? 'text-accent fill-accent' : 'text-muted-foreground'}`} />
              </button>
            ))}
          </div>
          <Textarea value={review} onChange={(e) => setReview(e.target.value)} placeholder="Tell us about your experience…" data-testid="review-input" />
          <DialogFooter>
            <Button onClick={submitRating} className="bg-accent font-bold" data-testid="submit-rating-btn">Submit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
