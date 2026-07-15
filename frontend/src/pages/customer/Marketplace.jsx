import React, { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Filter, ArrowRight } from "lucide-react";
import * as Icons from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function Marketplace() {
  const navigate = useNavigate();
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
      <div className="cb-overline text-accent">Service marketplace</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1">Browse {services.length}+ legal services</h1>
      <p className="text-muted-foreground font-medium mt-2">Transparent INR pricing. Verified vendors. Pan-India coverage.</p>

      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search services…" className="pl-10" data-testid="marketplace-search" />
        </div>
      </div>

      {/* Category chips */}
      <div className="mt-5 flex gap-2 overflow-x-auto pb-2">
        <button onClick={() => setCat("all")} className={`px-4 py-2 rounded-full text-sm font-bold shrink-0 ${cat === "all" ? 'bg-primary text-white' : 'bg-secondary text-foreground'}`} data-testid="cat-all">All</button>
        {categories.map(c => (
          <button key={c} onClick={() => setCat(c)} className={`px-4 py-2 rounded-full text-sm font-bold shrink-0 ${cat === c ? 'bg-primary text-white' : 'bg-secondary text-foreground'}`} data-testid={`cat-${c.replace(/\s+/g, '-').toLowerCase()}`}>{c}</button>
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
    </PageContainer>
  );
}
