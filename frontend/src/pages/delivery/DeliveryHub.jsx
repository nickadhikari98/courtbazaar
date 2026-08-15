import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Truck, MapPin, CheckCircle2, Navigation } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import EmptyState from "@/components/shared/EmptyState";

export default function DeliveryHub() {
  const [orders, setOrders] = useState([]);
  const [integrations, setIntegrations] = useState({});
  const [otpOpen, setOtpOpen] = useState(false);
  const [otp, setOtp] = useState("");
  const [activeOrder, setActiveOrder] = useState(null);

  const load = async () => {
    const [q, i] = await Promise.all([api.get("/delivery/queue"), api.get("/delivery/integrations")]);
    setOrders(q.data || []);
    setIntegrations(i.data || {});
  };
  useEffect(() => { load(); }, []);

  const accept = async (id) => {
    try {
      await api.post(`/delivery/${id}/accept`);
      toast.success("Delivery accepted");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const updateLoc = async (id) => {
    // Random walk near Delhi for demo
    const lat = 28.6139 + (Math.random() - 0.5) * 0.05;
    const lng = 77.2090 + (Math.random() - 0.5) * 0.05;
    try {
      await api.post(`/delivery/${id}/location`, { lat, lng, note: "Tracking ping" });
      toast.success("Location updated");
    } catch { toast.error("Failed"); }
  };

  const completeDelivery = async () => {
    try {
      await api.post(`/delivery/${activeOrder.order_id}/complete`, { otp });
      toast.success("Delivered!");
      setOtpOpen(false);
      setOtp("");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Invalid OTP"); }
  };

  return (
    <PageContainer className="max-w-5xl">
      <div className="cb-overline text-accent">Delivery hub</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-2">Pickup & dispatch</h1>

      <div className="mt-4 flex flex-wrap gap-2 mb-6">
        <Badge className="bg-emerald-100 text-emerald-700 border-0 font-bold">Own network: Active</Badge>
        <Badge className={integrations.dunzo_enabled ? "bg-emerald-100 text-emerald-700 border-0" : "bg-secondary text-muted-foreground border-0"}>
          Dunzo: {integrations.dunzo_enabled ? "Connected" : "Add DUNZO_API_KEY"}
        </Badge>
        <Badge className={integrations.borzo_enabled ? "bg-emerald-100 text-emerald-700 border-0" : "bg-secondary text-muted-foreground border-0"}>
          Borzo: {integrations.borzo_enabled ? "Connected" : "Add BORZO_API_KEY"}
        </Badge>
      </div>

      <div className="space-y-3">
        {orders.length === 0 && <EmptyState icon={Truck} title="No deliveries in queue" />}
        {orders.map(o => (
          <Card key={o.order_id} className="dashboard-card border-none" data-testid={`delivery-order-${o.order_id}`}>
            <CardContent className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs font-bold text-muted-foreground">{o.order_id}</span>
                    <Badge className="bg-accent/10 text-accent border-0 text-2xs uppercase font-bold">{o.status.replace(/_/g, ' ')}</Badge>
                    <Badge variant="outline" className="text-2xs capitalize">{o.delivery_option}</Badge>
                  </div>
                  <div className="font-display font-bold">{o.court_name}</div>
                  <div className="text-xs text-muted-foreground font-medium mt-1 flex items-center gap-1.5"><MapPin className="w-3 h-3" /> {o.delivery_address || o.court_name}</div>
                  <div className="text-xs font-semibold mt-1">Customer: {o.user_name} · {o.user_phone || "—"}</div>
                </div>
                <div className="flex flex-col gap-2 items-end">
                  <div className="font-display font-bold text-accent">{formatINR(o.pricing?.delivery_fee || 0)}</div>
                  {o.status === "ready" && !o.delivery_partner_id && (
                    <Button onClick={() => accept(o.order_id)} className="bg-accent font-bold" size="sm" data-testid={`accept-delivery-${o.order_id}`}>
                      Accept pickup
                    </Button>
                  )}
                  {o.status === "out_for_delivery" && (
                    <div className="flex gap-2">
                      <Button onClick={() => updateLoc(o.order_id)} variant="outline" size="sm" data-testid={`update-loc-${o.order_id}`}>
                        <Navigation className="w-3 h-3 mr-1" /> Ping
                      </Button>
                      <Button onClick={() => { setActiveOrder(o); setOtpOpen(true); }} className="bg-emerald-600 font-bold" size="sm" data-testid={`complete-delivery-${o.order_id}`}>
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Complete
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              {o.delivery_location && (
                <div className="mt-3 p-3 bg-secondary rounded-lg text-xs font-semibold flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-accent" />
                  Last ping: {o.delivery_location.lat?.toFixed(4)}, {o.delivery_location.lng?.toFixed(4)} · {new Date(o.delivery_location.updated_at).toLocaleTimeString()}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={otpOpen} onOpenChange={setOtpOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Confirm delivery with OTP</DialogTitle></DialogHeader>
          <div className="text-sm text-muted-foreground font-medium">Ask the customer for the 6-digit OTP they received. Demo OTP: <b className="text-accent">123456</b></div>
          <Input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="6-digit OTP" maxLength={6} data-testid="delivery-otp-input" />
          <DialogFooter><Button onClick={completeDelivery} className="bg-emerald-600 font-bold" data-testid="delivery-otp-submit">Confirm delivery</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
