import React, { useEffect, useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Filter, ArrowRight, Gavel, Scale, CreditCard, Building2 } from "lucide-react";
import * as Icons from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { isFeatureEnabled } from "@/config/featureFlags";

// Non-catalog offerings (not `db.services` rows — separate pages) that
// still belong on Marketplace per the founder's visible-service list.
const PROFESSIONAL_SERVICES = [
  { to: "/hire-proxy-counsel", icon: Gavel, label: "Hire Proxy Counsel", detail: "Request an advocate to appear on your behalf", capability: "can_hire_proxy_counsel" },
  { to: "/hire-counsel", icon: Scale, label: "Hire Counsel", detail: "Full legal representation — onboarding in progress", capability: "can_hire_proxy_counsel", flag: "services.hireCounsel" },
  { to: "/subscription", icon: CreditCard, label: "Packages", detail: "Subscription bundles for frequent filers" },
  { to: "/courts", icon: Building2, label: "Court Directory", detail: "Browse every court CourtBazaar covers" },
];

export default function Marketplace() {
  const navigate = useNavigate();
  const { hasCapability } = useAuth();
  const [services, setServices] = useState([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/services").then(r => { setServices(r.data); setLoading(false); });
  }, []);

  const categories = useMemo(() => Array.from(new Set(services.map(s => s.category))), [services]);
  const filtered = services.filter(s =>
    (cat === "all" || s.category === cat) &&
    (!q || s.name.toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <PageContainer>
      <PageHeader eyebrow="Service marketplace" title={`Browse ${services.length}+ legal services`}
                  description="Transparent INR pricing. Verified vendors. Pan-India coverage."
                  titleClassName="lg:text-4xl" />

      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search services…" className="pl-10" data-testid="marketplace-search" />
        </div>
      </div>

      {/* Category chips */}
      <div className="mt-5 flex gap-2 overflow-x-auto pb-2">
        <Button type="button" size="sm" variant={cat === "all" ? "default" : "ghost"}
                className={`rounded-full shrink-0 font-bold ${cat === "all" ? "" : "bg-secondary text-foreground hover:bg-secondary/80"}`}
                onClick={() => setCat("all")} data-testid="cat-all">All</Button>
        {categories.map(c => (
          <Button key={c} type="button" size="sm" variant={cat === c ? "default" : "ghost"}
                  className={`rounded-full shrink-0 font-bold ${cat === c ? "" : "bg-secondary text-foreground hover:bg-secondary/80"}`}
                  onClick={() => setCat(c)} data-testid={`cat-${c.replace(/\s+/g, '-').toLowerCase()}`}>{c}</Button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? Array(9).fill(0).map((_, i) => <div key={i} className="h-32 shimmer rounded-xl"></div>) :
          filtered.map(s => {
            const Icon = Icons[s.icon] || Icons.FileText;
            return (
              <Card key={s.service_id} className="dashboard-card border-none hover:shadow-md transition-all" data-testid={`marketplace-svc-${s.service_id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-11 h-11 rounded-xl bg-accent/10 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-accent" />
                    </div>
                    <Badge variant="outline" className="text-2xs font-bold uppercase">{s.turnaround_hours}h TAT</Badge>
                  </div>
                  <div className="font-display font-bold text-base leading-tight">{s.name}</div>
                  <div className="cb-overline mt-1">{s.category}</div>
                  <div className="mt-3 flex items-end justify-between">
                    <div>
                      <div className="font-display font-black text-xl">{formatINR(s.base_price)}</div>
                      <div className="text-xs text-muted-foreground font-semibold">{s.unit}</div>
                    </div>
                    <Button size="sm" onClick={() => navigate(`/order/new?service=${s.service_id}`)} className="bg-primary font-bold" data-testid={`order-${s.service_id}`}>
                      Order <ArrowRight className="w-3 h-3 ml-1" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
      </div>

      {/* Non-catalog offerings — Proxy Counsel/Counsel/Packages/Court
          Directory aren't db.services rows, so they're links here rather
          than part of the filtered grid above. */}
      <div className="mt-10">
        <div className="cb-overline text-accent">Beyond the catalog</div>
        <h2 className="font-display font-bold text-2xl mt-1 tracking-tight mb-4">Professional Legal Services</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {PROFESSIONAL_SERVICES
            .filter((s) => (!s.capability || hasCapability(s.capability)) && (!s.flag || isFeatureEnabled(s.flag)))
            .map((s) => (
              <Link key={s.to} to={s.to} className="dashboard-card border-none hover:shadow-md transition-all p-5 block" data-testid={`marketplace-pro-${s.to.replace(/\//g, '')}`}>
                <div className="w-11 h-11 rounded-xl bg-accent/10 flex items-center justify-center mb-3">
                  <s.icon className="w-5 h-5 text-accent" />
                </div>
                <div className="font-display font-bold text-base leading-tight">{s.label}</div>
                <div className="text-xs text-muted-foreground font-medium mt-1">{s.detail}</div>
              </Link>
            ))}
        </div>
      </div>
    </PageContainer>
  );
}
