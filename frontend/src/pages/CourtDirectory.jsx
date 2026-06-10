import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Building2, ShieldCheck, Search, MapPin } from "lucide-react";

export default function CourtDirectory() {
  const [states, setStates] = useState([]);
  const [activeState, setActiveState] = useState(null);
  const [courts, setCourts] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/states").then(r => {
      setStates(r.data);
      if (r.data.length) {
        setActiveState(r.data[0].state_id);
      }
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (activeState) api.get("/courts", { params: { state_id: activeState } }).then(r => setCourts(r.data));
  }, [activeState]);

  const filtered = courts.filter(c => !q || c.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
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
              <Card key={c.court_id} className="dashboard-card border-none hover:shadow-md transition-all" data-testid={`court-${c.court_id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center shrink-0">
                      <Building2 className="w-5 h-5 text-accent" />
                    </div>
                    <div className="min-w-0">
                      <div className="font-display font-bold text-base leading-tight">{c.name}</div>
                      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5"><MapPin className="w-3 h-3" /> {c.address}</div>
                      <div className="mt-2 flex items-center gap-2">
                        <Badge className="bg-emerald-100 text-emerald-700 border-0 text-[10px] uppercase font-bold">{c.type?.replace('_', ' ')}</Badge>
                        <Badge variant="outline" className="text-[10px] font-bold flex items-center gap-1">
                          <ShieldCheck className="w-3 h-3" /> Verified
                        </Badge>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
