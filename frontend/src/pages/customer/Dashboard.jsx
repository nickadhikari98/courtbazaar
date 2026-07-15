import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import PageContainer from "@/components/layout/PageContainer";
import {
  Plus, Printer, FileText, Gavel, Stamp, Package, BookOpen, Sparkles, Truck, ArrowRight,
  Wallet, ShieldCheck, TrendingUp, Clock, Type, Scale, FileSignature
} from "lucide-react";

const quickServices = [
  { id: "svc_bw_photocopy", icon: Printer, label: "B&W Photocopy", price: "₹1/pg", color: "bg-amber-50", iconColor: "text-amber-700" },
  { id: "svc_bw_print", icon: Printer, label: "B&W Print", price: "₹2/pg", color: "bg-blue-50", iconColor: "text-blue-700" },
  { id: "svc_spiral_binding", icon: BookOpen, label: "Spiral Binding", price: "₹40", color: "bg-emerald-50", iconColor: "text-emerald-700" },
  { id: "svc_hard_binding", icon: Package, label: "Hard Binding", price: "₹250", color: "bg-rose-50", iconColor: "text-rose-700" },
  { id: "svc_efile_hc", icon: Gavel, label: "High Court Filing", price: "₹900", color: "bg-purple-50", iconColor: "text-purple-700" },
  { id: "svc_efile_district", icon: Scale, label: "District Filing", price: "₹500", color: "bg-cyan-50", iconColor: "text-cyan-700" },
  { id: "svc_notary_doc", icon: Stamp, label: "Notarization", price: "₹100", color: "bg-yellow-50", iconColor: "text-yellow-700" },
  { id: "svc_typing_petition", icon: Type, label: "Petition Typing", price: "₹15/pg", color: "bg-orange-50", iconColor: "text-orange-700" },
  { id: "svc_court_bundle", icon: FileText, label: "Court Bundle", price: "₹500", color: "bg-indigo-50", iconColor: "text-indigo-700" },
  { id: "svc_court_runner", icon: Truck, label: "Court Runner", price: "₹500", color: "bg-teal-50", iconColor: "text-teal-700" },
  { id: "svc_affidavit_draft", icon: FileSignature, label: "Affidavit", price: "₹300", color: "bg-pink-50", iconColor: "text-pink-700" },
  { id: "svc_ocr", icon: Sparkles, label: "OCR + AI", price: "₹5/pg", color: "bg-violet-50", iconColor: "text-violet-700" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/orders").then((r) => setOrders(r.data || [])).finally(() => setLoading(false));
  }, []);

  const active = orders.filter(o => !["completed", "delivered", "cancelled"].includes(o.status));
  const completed = orders.filter(o => o.status === "completed" || o.status === "delivered");

  const stats = [
    { label: "Active Orders", value: active.length, icon: Clock, color: "bg-accent/10 text-accent" },
    { label: "Completed", value: completed.length, icon: ShieldCheck, color: "bg-emerald-100 text-emerald-700" },
    { label: "Wallet", value: formatINR(user?.wallet_balance || 0), icon: Wallet, color: "bg-blue-100 text-blue-700" },
    { label: "Total Spent", value: formatINR(orders.reduce((s,o) => s + (o.pricing?.total||0), 0)), icon: TrendingUp, color: "bg-purple-100 text-purple-700" },
  ];

  return (
    <PageContainer>
      {/* Hero CTA */}
      <div className="relative bg-primary text-white rounded-3xl p-8 lg:p-10 mb-8 overflow-hidden" data-testid="dashboard-hero">
        <div className="absolute inset-0 cb-grain opacity-30"></div>
        <div className="relative grid grid-cols-1 lg:grid-cols-3 gap-6 items-center">
          <div className="lg:col-span-2">
            <Badge className="bg-accent text-white border-0 mb-3 px-2.5 py-1 font-bold">SUB-30s ORDER</Badge>
            <h1 className="font-display font-black text-4xl lg:text-5xl tracking-tighter leading-tight">
              Place your next court order in 30 seconds.
            </h1>
            <p className="mt-3 text-white/70 font-medium">Upload, pick court, choose services, pay. We handle everything else.</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button onClick={() => navigate("/order/new")} size="lg" className="bg-accent hover:bg-accent/90 h-12 font-bold" data-testid="dashboard-new-order-btn">
                <Plus className="w-4 h-4 mr-2" /> New Order
              </Button>
              <Button onClick={() => navigate("/ai")} variant="outline" size="lg" className="border-white text-white bg-transparent hover:bg-white hover:text-primary h-12 font-bold" data-testid="dashboard-ai-btn">
                <Sparkles className="w-4 h-4 mr-2" /> Ask AI Assistant
              </Button>
            </div>
          </div>
          <div className="hidden lg:flex justify-end">
            <div className="w-44 h-44 bg-white/10 rounded-3xl flex items-center justify-center backdrop-blur-md border border-white/20">
              <Scale className="w-24 h-24 text-accent" strokeWidth={1.2} />
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
          <Card key={s.label} className="dashboard-card border-none" data-testid={`dash-stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <CardContent className="p-5">
              <div className={`w-10 h-10 rounded-lg ${s.color} flex items-center justify-center mb-3`}>
                <s.icon className="w-5 h-5" />
              </div>
              <div className="cb-overline">{s.label}</div>
              <div className="font-display font-black text-2xl mt-1 tracking-tight">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick services (Zepto-style) */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="cb-overline text-accent">Quick order</div>
            <h2 className="font-display font-bold text-2xl mt-1 tracking-tight">Tap to start</h2>
          </div>
          <Link to="/marketplace" className="text-sm font-bold text-accent hover:underline" data-testid="dash-view-all-services">View all services →</Link>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          {quickServices.map((s) => (
            <button
              key={s.id}
              onClick={() => navigate(`/order/new?service=${s.id}`)}
              className="bento-card p-4 text-left group"
              data-testid={`quick-service-${s.id}`}
            >
              <div className={`w-11 h-11 rounded-xl ${s.color} flex items-center justify-center mb-3 group-hover:scale-105 transition-transform`}>
                <s.icon className={`w-5 h-5 ${s.iconColor}`} strokeWidth={2} />
              </div>
              <div className="font-display font-bold text-sm leading-tight">{s.label}</div>
              <div className="text-xs text-muted-foreground font-semibold mt-1">{s.price}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Active orders */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-bold text-2xl tracking-tight">Active orders</h2>
            <Link to="/orders" className="text-sm font-bold text-accent hover:underline" data-testid="dash-view-orders">All orders →</Link>
          </div>
          {loading ? (
            <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-24 shimmer rounded-xl"></div>)}</div>
          ) : active.length === 0 ? (
            <Card className="border-dashed border-2">
              <CardContent className="p-10 text-center">
                <Package className="w-12 h-12 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
                <div className="font-display font-bold text-lg">No active orders</div>
                <p className="text-sm text-muted-foreground mt-1">Place your first order — it takes 30 seconds.</p>
                <Button onClick={() => navigate("/order/new")} className="mt-4 bg-accent hover:bg-accent/90 font-bold" data-testid="dash-empty-order-btn">
                  <Plus className="w-4 h-4 mr-2" /> Place Order
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {active.slice(0, 5).map((o) => (
                <Link to={`/orders/${o.order_id}`} key={o.order_id} className="block" data-testid={`active-order-${o.order_id}`}>
                  <Card className="dashboard-card hover:shadow-md transition-all">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono text-xs font-bold text-muted-foreground">{o.order_id}</span>
                            <Badge className="bg-accent/10 text-accent border-0 text-2xs uppercase font-bold">{o.status.replace("_", " ")}</Badge>
                          </div>
                          <div className="font-display font-bold text-lg truncate">{o.court_name || o.court_id}</div>
                          <div className="text-sm text-muted-foreground font-medium mt-0.5">{o.services?.length || 0} services · {o.delivery_option} delivery</div>
                        </div>
                        <div className="text-right">
                          <div className="font-display font-black text-lg">{formatINR(o.pricing?.total || 0)}</div>
                          <ArrowRight className="w-4 h-4 ml-auto mt-1 text-muted-foreground" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Right rail */}
        <div className="space-y-4">
          <Card className="dashboard-card" data-testid="ai-promo-card">
            <CardContent className="p-5">
              <div className="cb-overline text-accent">AI Assistant</div>
              <div className="font-display font-bold text-lg mt-2 leading-tight">
                Need a filing checklist or defect check?
              </div>
              <p className="text-sm text-muted-foreground font-medium mt-1">Powered by Claude. Indian legal context.</p>
              <Button onClick={() => navigate("/ai")} variant="outline" className="mt-4 w-full font-bold" data-testid="dash-ai-cta">
                <Sparkles className="w-4 h-4 mr-2 text-accent" /> Start Chat
              </Button>
            </CardContent>
          </Card>

          {user?.subscription === "free" && (
            <Card className="bg-gradient-to-br from-accent/90 to-accent text-white border-none" data-testid="upgrade-card">
              <CardContent className="p-5">
                <div className="cb-overline text-white/70">Upgrade</div>
                <div className="font-display font-bold text-xl mt-2 leading-tight">Save 10% with Advocate Pro</div>
                <p className="text-sm text-white/80 font-medium mt-1">Priority support · Faster TAT · ₹499/mo</p>
                <Button onClick={() => navigate("/subscription")} className="mt-4 w-full bg-white text-accent hover:bg-white/90 font-bold" data-testid="dash-upgrade-btn">
                  See Plans
                </Button>
              </CardContent>
            </Card>
          )}

          <Card className="dashboard-card" data-testid="onboarding-progress-card">
            <CardContent className="p-5">
              <div className="cb-overline">Profile readiness</div>
              <div className="mt-3 flex items-center justify-between mb-2">
                <span className="text-sm font-bold">{user?.bar_council_id ? "85%" : "40%"} complete</span>
              </div>
              <Progress value={user?.bar_council_id ? 85 : 40} className="h-2" />
              <Link to="/profile" className="mt-3 inline-block text-xs font-bold text-accent hover:underline" data-testid="dash-complete-profile">
                Complete profile →
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
