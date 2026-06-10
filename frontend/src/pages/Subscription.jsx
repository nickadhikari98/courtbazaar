import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { CheckCircle2, Crown, Star, Building, Zap } from "lucide-react";

const planIcon = { free: Star, advocate_pro: Zap, law_firm: Building, enterprise: Crown };

export default function Subscription() {
  const { user, refresh } = useAuth();
  const [plans, setPlans] = useState({});

  useEffect(() => { api.get("/subscriptions/plans").then(r => setPlans(r.data)); }, []);

  const activate = async (planKey) => {
    try {
      await api.post("/subscriptions/activate", { plan: planKey });
      toast.success(`${plans[planKey].name} activated!`);
      await refresh();
    } catch { toast.error("Could not activate plan"); }
  };

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto">
      <div className="cb-overline text-accent">Plans & subscription</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1">Choose your tier</h1>
      <p className="text-muted-foreground font-medium mt-2">Cancel anytime. GST invoices auto-generated.</p>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(plans).map(([key, p]) => {
          const Icon = planIcon[key] || Star;
          const active = user?.subscription === key;
          const highlight = key === "advocate_pro";
          return (
            <Card key={key} className={`relative ${highlight ? 'border-accent border-2 shadow-lg' : 'dashboard-card border-none'}`} data-testid={`plan-${key}`}>
              {highlight && <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 bg-accent text-white border-0 font-bold">MOST POPULAR</Badge>}
              <CardContent className="p-6">
                <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center mb-3">
                  <Icon className="w-5 h-5 text-accent" />
                </div>
                <div className="font-display font-bold text-xl">{p.name}</div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="font-display font-black text-4xl tracking-tighter">{formatINR(p.price)}</span>
                  {p.price > 0 && <span className="text-xs font-semibold text-muted-foreground">/month</span>}
                </div>
                <div className="mt-5 space-y-2.5">
                  {p.features.map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="font-medium">{f}</span>
                    </div>
                  ))}
                </div>
                <Button
                  onClick={() => activate(key)}
                  disabled={active}
                  className={`mt-6 w-full font-bold ${active ? 'bg-secondary text-foreground' : highlight ? 'bg-accent hover:bg-accent/90' : 'bg-primary hover:bg-primary/90'}`}
                  data-testid={`activate-${key}`}
                >
                  {active ? "Current Plan" : "Activate"}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
