import React, { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Search, Loader2 } from "lucide-react";
import { getAvailableAdvocates } from "@/lib/advocateRecommendationsApi";
import CounselCard from "./CounselCard";

/* Fallback path — only ever mounted once the customer clicks "Search More
   Counsels" on CounselDiscoveryPanel (never shown up front, per the
   founder's "AI recommendations are always the default" direction).
   Reuses the exact same getAvailableAdvocates source as the AI
   recommendation step; the only difference is presentation (a
   name/court/expertise text filter over the same pool instead of a
   ranked top list) and that it's opt-in. */
export default function ManualCounselSearch({ onSelect, onViewProfile, selectingId }) {
  const [status, setStatus] = useState("loading");
  const [advocates, setAdvocates] = useState([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    getAvailableAdvocates({})
      .then(({ advocates: list }) => { setAdvocates(list || []); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = !q ? advocates : advocates.filter((a) =>
    a.name?.toLowerCase().includes(q)
    || a.practice_areas?.some((p) => p.toLowerCase().includes(q))
    || a.primary_courts?.some((c) => c.toLowerCase().includes(q)));

  return (
    <div className="border-t border-dashed pt-6" data-testid="manual-counsel-search">
      <div className="cb-overline text-accent">Manual Search</div>
      <h3 className="font-display font-bold text-lg tracking-tight mt-1 mb-3">Search More Counsels</h3>

      <div className="relative mb-4 max-w-sm">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9" placeholder="Search by name, court, or expertise"
          value={query} onChange={(e) => setQuery(e.target.value)} data-testid="manual-search-input"
        />
      </div>

      {status === "loading" && (
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground py-8">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading counsels…
        </div>
      )}
      {status === "error" && (
        <p className="text-sm text-muted-foreground text-center py-8">Couldn't load counsels right now.</p>
      )}
      {status === "ready" && !filtered.length && (
        <p className="text-sm text-muted-foreground text-center py-8">No counsels match &ldquo;{query}&rdquo;.</p>
      )}
      {status === "ready" && !!filtered.length && (
        <div className="grid sm:grid-cols-2 gap-4">
          {filtered.map((a) => (
            <CounselCard
              key={a.advocate_id} counsel={a} onViewProfile={onViewProfile} onSelect={onSelect}
              selecting={selectingId === a.advocate_id}
              disabled={!!selectingId && selectingId !== a.advocate_id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
