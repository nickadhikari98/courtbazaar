import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Building2, ShieldCheck, Search, MapPin, Lock } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function CourtDirectory() {
  const [states, setStates] = useState([]);
  const [activeState, setActiveState] = useState(null);
  const [courts, setCourts] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get("/states").then(r => {
      setStates(r.data);
      // Default to Delhi (the serviceable state)
      const delhi = r.data.find(s => s.state_id === "state_delhi");
      if (delhi) setActiveState(delhi.state_id);
      else if (r.data.length) setActiveState(r.data[0].state_id);
    });
  }, []);

  useEffect(() => {
    if (activeState) api.get("/courts", { params: { state_id: activeState } }).then(r => setCourts(r.data));
  }, [activeState]);

  const filtered = courts.filter(c => !q || c.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <PageContainer>
      <div className="cb-overline text-accent">Court directory</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1">India → State → Court</h1>
      <p className="text-muted-foreground font-medium mt-2">Browse our vendor network across India's legal forums.</p>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1">
          <div className="cb-overline mb-2">States ({states.length})</div>
          <div className="space-y-1">
            {states.map(s => (
              <button key={s.state_id} onClick={() => setActiveState(s.state_id)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold transition-all ${activeState === s.state_id ? 'bg-primary text-white' : 'hover:bg-secondary text-foreground'}`}
                data-testid={`state-${s.state_id}`}>
                {s.name} <span className="text-xs opacity-70">({s.code})</span>
              </button>
            ))}
          </div>
        </div>

        <div className="lg:col-span-3">
          <div className="relative mb-4">
            <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search courts…" className="pl-10" data-testid="courts-search" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {filtered.map(c => (
              <Card key={c.court_id} className={`dashboard-card border-none hover:shadow-md transition-all ${c.serviceable === false ? 'opacity-70' : ''}`} data-testid={`court-${c.court_id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-lg ${c.serviceable === false ? 'bg-secondary' : 'bg-accent/10'} flex items-center justify-center shrink-0`}>
                      <Building2 className={`w-5 h-5 ${c.serviceable === false ? 'text-muted-foreground' : 'text-accent'}`} />
                    </div>
                    <div className="min-w-0">
                      <div className="font-display font-bold text-base leading-tight">{c.name}</div>
                      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5"><MapPin className="w-3 h-3" /> {c.address}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Badge className="bg-emerald-100 text-emerald-700 border-0 text-2xs uppercase font-bold">{c.type?.replace('_', ' ')}</Badge>
                        {c.serviceable !== false ? (
                          <Badge variant="outline" className="text-2xs font-bold flex items-center gap-1 border-emerald-300 text-emerald-700">
                            <ShieldCheck className="w-3 h-3" /> Serviceable
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-2xs font-bold flex items-center gap-1 border-amber-300 text-amber-700">
                            <Lock className="w-3 h-3" /> Coming Soon
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </PageContainer>
  );
}
