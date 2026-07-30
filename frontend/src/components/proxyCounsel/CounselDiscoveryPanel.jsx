import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Check, Loader2, RefreshCw, Search, Sparkles, Users } from "lucide-react";
import { getAvailableAdvocates } from "@/lib/advocateRecommendationsApi";
import CounselCard from "./CounselCard";
import CounselProfileDialog from "./CounselProfileDialog";
import ManualCounselSearch from "./ManualCounselSearch";

const MATCH_FACTORS = ["Court", "Expertise", "Experience", "Availability", "Ratings"];

/* Step 2 of the Proxy Counsel request flow (see HireProxyCounsel.jsx): an
   explicit AI Recommendation / Search Manually toggle, mutually exclusive —
   switching tabs swaps which panel is visible, it never stacks both. AI
   stays the default tab (fetched immediately on mount, no input required)
   for the customer who wants the best-matched counsel found for them;
   Search Manually is for the customer who already knows who they want and
   would rather look them up directly, not sift through a ranked list.

   Selecting a counsel (from either tab) is handled entirely by the parent
   via `onSelect` — this component never calls createHearingRequest itself,
   so both paths share one create+navigate implementation. `selectingId` is
   the advocate_id currently being submitted (parent-owned), so the right
   card shows a spinner without this component needing its own submission
   state. */
export default function CounselDiscoveryPanel({ context, onSelect, selectingId, excludeAdvocateId }) {
  const [mode, setMode] = useState("ai"); // "ai" | "manual"
  const [status, setStatus] = useState("loading");
  const [advocates, setAdvocates] = useState([]);
  const [profileCounsel, setProfileCounsel] = useState(null);

  const fetchRecommendations = () => {
    setStatus("loading");
    getAvailableAdvocates(context)
      .then(({ advocates: list }) => {
        // Set only when arriving via "End Negotiation" — leaves the counsel
        // who didn't work out off the AI list without hard-blocking a
        // deliberate re-pick through Search Manually.
        const filtered = excludeAdvocateId ? (list || []).filter((a) => a.advocate_id !== excludeAdvocateId) : (list || []);
        setAdvocates(filtered);
        setStatus(filtered.length ? "ready" : "empty");
      })
      .catch(() => setStatus("error"));
  };

  useEffect(() => {
    fetchRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one fetch per submitted request; context is fixed for the lifetime of this step
  }, []);

  return (
    <div>
      <div className="cb-overline text-accent">Proxy Counsel</div>
      <h2 className="font-display font-bold text-xl tracking-tight mt-1 mb-4">Find a Proxy Counsel</h2>

      <Tabs value={mode} onValueChange={setMode} className="mb-4">
        <TabsList>
          <TabsTrigger value="ai" data-testid="discovery-mode-ai">
            <Sparkles className="w-3.5 h-3.5 mr-1.5" /> AI Recommendation
          </TabsTrigger>
          <TabsTrigger value="manual" data-testid="discovery-mode-manual">
            <Search className="w-3.5 h-3.5 mr-1.5" /> Search Manually
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {mode === "ai" && (
        <>
          {status === "loading" && (
            <Card className="border-dashed border-2" data-testid="recommendations-loading">
              <CardContent className="p-8 text-center">
                <Loader2 className="w-8 h-8 mx-auto text-accent animate-spin mb-3" />
                <p className="font-display font-bold mb-3">Finding the best proxy counsels...</p>
                <p className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-2">Matching based on</p>
                <ul className="space-y-1.5 text-sm max-w-[220px] mx-auto text-left mb-4">
                  {MATCH_FACTORS.map((f) => (
                    <li key={f} className="flex items-center gap-2"><Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> {f}</li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">Loading…</p>
              </CardContent>
            </Card>
          )}

          {status === "error" && (
            <Card className="border-dashed border-2" data-testid="recommendations-error">
              <CardContent className="p-8 text-center">
                <p className="text-sm text-muted-foreground mb-3">Couldn't load recommendations right now.</p>
                <Button type="button" variant="outline" size="sm" onClick={fetchRecommendations}>
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry
                </Button>
              </CardContent>
            </Card>
          )}

          {status === "empty" && (
            <Card className="border-dashed border-2" data-testid="recommendations-empty">
              <CardContent className="p-8 text-center">
                <Users className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
                <p className="text-sm text-muted-foreground mb-3">No AI recommendations for this request yet.</p>
                <Button type="button" variant="outline" size="sm" onClick={() => setMode("manual")} data-testid="empty-switch-to-manual">
                  <Search className="w-3.5 h-3.5 mr-1.5" /> Search Manually Instead
                </Button>
              </CardContent>
            </Card>
          )}

          {status === "ready" && (
            <div className="grid sm:grid-cols-2 gap-4">
              {advocates.map((a) => (
                <CounselCard
                  key={a.advocate_id} counsel={a} onViewProfile={setProfileCounsel}
                  onSelect={onSelect} selecting={selectingId === a.advocate_id}
                  disabled={!!selectingId && selectingId !== a.advocate_id}
                />
              ))}
            </div>
          )}
        </>
      )}

      {mode === "manual" && (
        <ManualCounselSearch onSelect={onSelect} onViewProfile={setProfileCounsel} selectingId={selectingId} />
      )}

      <CounselProfileDialog counsel={profileCounsel} onOpenChange={(v) => !v && setProfileCounsel(null)} />
    </div>
  );
}
