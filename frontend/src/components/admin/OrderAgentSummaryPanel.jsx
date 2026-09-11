import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, AlertTriangle, AlertCircle, Info, CheckCircle2, Loader2, ArrowRight } from "lucide-react";
import { getOrderAgentSummary } from "@/lib/orderAgentApi";

/* Order Management Agent — "Needs Attention" panel. Read-only: calls
   GET /admin/order-agent/summary on demand (the "Analyze with AI" button
   below) and renders whatever comes back, including the degrade-gracefully
   shape (available: false) when GROQ_API_KEY isn't configured or the model
   call failed/timed out — the panel never blocks on the AI layer, same
   convention the backend route itself follows (see order_management_agent.py).
   On-demand rather than auto-run on mount, same "never auto-runs, only when
   admin explicitly asks" convention as the hearing-level "Summarize with AI"
   button in AdminHearingVerification.jsx — this call runs a real (token-
   metered) model request, so it shouldn't fire just from loading the page.

   Presentation only: every card below is built straight off state.open_flags
   (order_agent_tools.list_open_flags — flag_id/hearing_id/reason/
   agent_summary, written only by the agent's flag_for_admin_review tool).
   Nothing here filters, hides, or re-ranks a flag — REASON_META just maps
   each flag's existing `reason` to a priority/title/action for display; an
   unrecognized reason still renders (humanized, generic action) rather than
   being dropped. The model's free-text `summary` paragraph is intentionally
   not rendered — it can contain raw Markdown, and every fact in it is
   already covered, structured, by the cards + counts below.

   The "Analyze with AI" button is the ONE place that communicates AI request
   state (idle/analyzing/complete/unavailable) — there is no separate error
   banner or fallback message anywhere in this panel. Detected issue cards
   are built entirely from state.open_flags and stay fully visible regardless
   of whether the AI call itself succeeded or failed. */
const AI_BUTTON_META = {
  idle: { label: "Analyze with AI", icon: Sparkles, tone: "" },
  loading: { label: "Analyzing...", icon: Loader2, tone: "", spin: true },
  success: { label: "AI analysis complete", icon: CheckCircle2, tone: "text-emerald-600 border-emerald-200" },
  error: { label: "AI analysis unavailable", icon: AlertTriangle, tone: "text-red-600 border-red-200" },
};

const REASON_META = {
  disputed: {
    priority: "critical", title: "Dispute raised",
    action: "Resolve the dispute — resubmit the order sheet for review, or refund & cancel.",
  },
  verification_overdue: {
    priority: "critical", title: "Verification overdue",
    action: "Auto-release deadline has passed — verify or dispute the order sheet now.",
  },
  order_sheet_overdue: {
    priority: "critical", title: "Order sheet overdue",
    action: "Follow up with the proxy counsel to upload the court order sheet.",
  },
  escalated_unassigned: {
    priority: "critical", title: "Escalated — no counsel assigned",
    action: "Manually assign a proxy counsel or resolve the escalation.",
  },
  verification_approaching_auto_release: {
    priority: "warning", title: "Verification approaching deadline",
    action: "Verify or dispute soon — escrow auto-releases if no action is taken.",
  },
  payment_stalled: {
    priority: "warning", title: "Payment stalled",
    action: "Check with the client on why payment hasn't completed.",
  },
  payout_not_released: {
    priority: "warning", title: "Payout not released",
    action: "Order sheet is verified — release the payout to the proxy counsel.",
  },
  stalled: {
    priority: "info", title: "Stalled — no recent activity",
    action: "Review this hearing's history to see what's blocking progress.",
  },
};

const PRIORITY_META = {
  critical: { icon: AlertTriangle, label: "Critical", chip: "bg-red-100 text-red-700 border-red-200", card: "border-red-200 bg-red-50/60" },
  warning: { icon: AlertCircle, label: "Warning", chip: "bg-amber-100 text-amber-700 border-amber-200", card: "border-amber-200 bg-amber-50/60" },
  info: { icon: Info, label: "Info", chip: "bg-blue-100 text-blue-700 border-blue-200", card: "border-blue-200 bg-blue-50/60" },
};

function humanizeReason(reason) {
  return (reason || "Needs review").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function issueMeta(reason) {
  return REASON_META[reason] || {
    priority: "info",
    title: humanizeReason(reason),
    action: "Open this hearing to review and decide the next step.",
  };
}

function AttentionCard({ flag }) {
  const meta = issueMeta(flag.reason);
  const pMeta = PRIORITY_META[meta.priority];
  const Icon = pMeta.icon;

  return (
    <div className={`rounded-lg border p-3 min-w-0 ${pMeta.card}`}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" />
        <Badge variant="outline" className={`text-2xs font-bold uppercase tracking-wide ${pMeta.chip}`}>
          {pMeta.label}
        </Badge>
      </div>

      <div className="font-display font-bold text-sm mb-1 break-words">{meta.title}</div>

      {flag.agent_summary && (
        <p className="text-xs text-muted-foreground mb-2 line-clamp-2 break-words">{flag.agent_summary}</p>
      )}

      <div className="flex items-start gap-1.5 text-xs font-semibold">
        <ArrowRight className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        <span className="break-words">{meta.action}</span>
      </div>

      <div className="mt-2 pt-2 border-t border-black/5 text-2xs text-muted-foreground truncate" title={flag.hearing_id}>
        Hearing: {flag.hearing_id}
      </div>
    </div>
  );
}

export default function OrderAgentSummaryPanel() {
  const [state, setState] = useState(null); // null = not yet run
  const [aiStatus, setAiStatus] = useState("idle"); // idle | loading | success | error — AI REQUEST state only

  const runAnalysis = async () => {
    setAiStatus("loading");
    try {
      const data = await getOrderAgentSummary();
      setState(data);
      setAiStatus(data?.available ? "success" : "error");
    } catch {
      setState({ available: false, reason: "Request failed" });
      setAiStatus("error");
    }
  };

  const flags = state?.open_flags || [];
  const btn = AI_BUTTON_META[aiStatus];
  const BtnIcon = btn.icon;

  return (
    <Card className="dashboard-card border-none mb-6">
      <CardContent className="p-5">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <Sparkles className="w-4 h-4 text-accent flex-shrink-0" />
          <div className="font-display font-bold text-sm">Needs attention</div>
          <Badge variant="outline" className="text-2xs font-bold uppercase">Order Management Agent</Badge>
          {aiStatus !== "loading" && state && (
            <Badge
              variant="outline"
              className={`text-2xs font-bold uppercase ${
                flags.length > 0
                  ? "bg-red-100 text-red-700 border-red-200"
                  : "bg-emerald-100 text-emerald-700 border-emerald-200"
              }`}
            >
              {flags.length} {flags.length === 1 ? "issue" : "issues"}
            </Badge>
          )}
          <Button type="button" size="sm" variant="outline" onClick={runAnalysis} disabled={aiStatus === "loading"}
                  className={`ml-auto h-7 px-2.5 text-2xs font-bold uppercase tracking-wide ${btn.tone}`}>
            <BtnIcon className={`w-3.5 h-3.5 mr-1.5 ${btn.spin ? "animate-spin" : ""}`} />
            {btn.label}
          </Button>
        </div>

        {state === null && aiStatus === "idle" && (
          <p className="text-sm text-muted-foreground">Click "Analyze with AI" to check for hearings needing attention.</p>
        )}

        {aiStatus === "loading" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Checking the order book…
          </div>
        )}

        {/* Operational content leads — issue count/all-clear first, cards next.
            AI request status lives ONLY in the button above (idle/analyzing/
            complete/unavailable) — no separate error banner or fallback message
            here. Detected issue cards below are built entirely from
            state.open_flags and stay fully visible whether or not the AI call
            itself succeeded. */}
        {aiStatus !== "loading" && state && (
          <div className="mb-3">
            {flags.length > 0 ? (
              <p className="text-sm text-muted-foreground">
                {flags.length} issue{flags.length === 1 ? "" : "s"} require{flags.length === 1 ? "s" : ""} admin attention
              </p>
            ) : (
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-md px-3 py-2">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> No action required
              </div>
            )}
          </div>
        )}

        {aiStatus !== "loading" && flags.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {flags.map((f) => <AttentionCard key={f.flag_id} flag={f} />)}
          </div>
        )}

        {aiStatus !== "loading" && state && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground border-t pt-3">
            {Array.isArray(state.hearings) && <span>{state.hearings.length} hearings tracked</span>}
            {Array.isArray(state.escalated_hearings) && <span>{state.escalated_hearings.length} escalated</span>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
