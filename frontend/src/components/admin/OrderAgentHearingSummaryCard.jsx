import React, { useState, useEffect, useRef } from "react";
import { formatINR } from "@/lib/api";
import { humanizeHearingActivity } from "@/lib/hearingLifecycle";
import { getOrderAgentHearingSummary } from "@/lib/orderAgentApi";
import { ChevronDown, ChevronRight, Sparkles, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

/* Structured, glanceable presentation of the Order Management Agent's
   per-hearing summary — self-contained: owns the "Summarize with AI"
   trigger, its own loading/success/error state, and the fetch itself
   (GET /admin/order-agent/hearings/{id}/summary via orderAgentApi.js).
   Never auto-runs — only fires on the button click, same "only when admin
   explicitly asks" convention as the platform-wide panel. This is a pure
   presentation layer over the existing API response shape
   (order_management_agent.py::summarize_hearing) — it never calls a
   route beyond that one GET, never derives a fact the backend didn't
   already return, and the free-text `summary` the model wrote is used
   only for the AI Recommendation section, trimmed for length. Everything
   else (status, payment, timeline, attention level, next action) is read
   directly off aiSummary.hearing / .escrow / .matching_session — that data
   is returned by the backend regardless of whether the model call itself
   succeeded (order_management_agent.py's fallback_data), so it stays
   correct and is shown even when the AI layer errors out or times out. */

const ORDER_STATUS_META = {
  requested: { icon: "🕓", label: "Requested" },
  broadcast: { icon: "🔍", label: "Escrow Funded — Finding Counsel" },
  payment_pending: { icon: "💳", label: "Payment Pending" },
  accepted: { icon: "🤝", label: "Counsel Assigned" },
  documents_shared: { icon: "📄", label: "Documents Shared" },
  preparation: { icon: "🛠️", label: "In Preparation" },
  hearing_scheduled: { icon: "📅", label: "Hearing Scheduled" },
  hearing_completed: { icon: "⚖️", label: "Hearing Conducted — Order Sheet Pending" },
  verification_pending: { icon: "🕓", label: "Awaiting Verification" },
  verified: { icon: "✅", label: "Verified" },
  completed: { icon: "✅", label: "Completed — Paid Out" },
  rated: { icon: "✅", label: "Completed — Paid Out" },
  disputed: { icon: "⚠️", label: "Disputed" },
  rejected: { icon: "❌", label: "Rejected" },
  cancelled: { icon: "❌", label: "Cancelled" },
  expired: { icon: "⌛", label: "Expired" },
};

const ESCROW_STATUS_LABEL = {
  created: "Payment initiated",
  held: "Held in escrow",
  released: "Released to counsel",
  refunded: "Refunded to client",
};

const ATTENTION_META = {
  red: { icon: "🔴", label: "Immediate action required" },
  yellow: { icon: "🟡", label: "Review recommended" },
  green: { icon: "🟢", label: "No action required" },
};

const AUTO_RELEASE_DELAY_DAYS = 3; // display-only mirror of hearings.py's AUTO_RELEASE_DELAY_DAYS

// "Summarize with AI" trigger — label/icon/tone per fetch state. Retry is
// always possible (button re-enables as soon as loading ends, success or not).
const AI_BUTTON_META = {
  idle: { label: "Summarize with AI", icon: Sparkles, className: "text-accent" },
  loading: { label: "Analyzing...", icon: Loader2, className: "text-accent", spin: true },
  success: { label: "AI analysis complete", icon: CheckCircle2, className: "text-emerald-600" },
  error: { label: "AI analysis unavailable", icon: AlertTriangle, className: "text-red-600" },
};

function computeAttentionLevel(hearing, matchingSession) {
  if (!hearing) return "yellow";
  if (hearing.status === "disputed") return "red";
  if (matchingSession?.status === "escalated" && !hearing.proxy_counsel_user_id) return "red";
  if (hearing.status === "verification_pending" || hearing.status === "hearing_completed") return "yellow";
  return "green";
}

function nextActionText(hearing, escrow) {
  if (!hearing) return "No further data available for this hearing.";
  switch (hearing.status) {
    case "disputed":
      return "Awaiting admin resolution — resubmit the order sheet for another look, or refund & cancel.";
    case "verification_pending": {
      if (hearing.verification_pending_at) {
        const deadline = new Date(hearing.verification_pending_at);
        deadline.setDate(deadline.getDate() + AUTO_RELEASE_DELAY_DAYS);
        return `Awaiting the client to verify or dispute the order sheet. If no action is taken, escrow auto-releases on ${deadline.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}.`;
      }
      return "Awaiting the client to verify or dispute the order sheet.";
    }
    case "verified":
      return escrow?.status === "held"
        ? "Order sheet is verified — release the payout to the proxy counsel whenever ready."
        : "Order sheet is verified.";
    case "hearing_completed":
      return "Awaiting the proxy counsel to upload the court order sheet.";
    case "completed":
    case "rated":
      return "Payout has been released — no further action needed.";
    case "rejected":
    case "cancelled":
    case "expired":
      return "This request is closed — no further action possible.";
    default:
      return "This hearing is progressing normally through matching/scheduling.";
  }
}

// Defensive cleanup for the model's free-text `summary` — the backend asks
// for "plain text" (order_management_agent.py's SYSTEM_PROMPT) but GPT-OSS
// still occasionally emits Markdown decoration (**bold**, table pipes,
// `---` rules, `#` headers, `- ` bullets); this never shows raw in the UI.
function stripMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/\r/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^-{3,}\s*$/gm, "")
    .replace(/^\s*[-*•]\s+/gm, "")
    .replace(/\|/g, " ")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`(.*?)`/g, "$1")
    .replace(/\n{2,}/g, " ")
    .replace(/\n/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// The model's `summary` is written to narrate the whole hearing (per
// order_management_agent.py's SYSTEM_PROMPT, "ground your summary in status,
// how long it's been there, deadlines, whose turn it is") — not just a
// recommendation, so it can front-load a narrative/timeline recap before
// ever getting to what the Admin should actually do. Blindly taking its
// first N sentences (the old behavior) could surface that recap — IDs,
// timestamps, a play-by-play of "Request created, Fee agreed, Payment
// captured..." — inside "AI Recommendation", where only Technical Details
// should hold that. This extracts just the actionable part: sentences that
// read like a recommendation (contain an action/advisory cue) and don't look
// like raw data. If nothing in the response reads as an actual
// recommendation, no AI Recommendation section renders at all — this never
// fabricates one from the structured hearing fields, which would blur the
// system-data/AI-content line section 3 above exists to keep.
const RAW_DATA_SENTENCE = /\b[a-z]+_[a-z0-9]{5,}\b|\d{4}-\d{2}-\d{2}/i;
const RECOMMENDATION_SIGNAL = /\b(recommend|suggest|advis|should|consider|release the|verify the|resolve|dispute|follow[- ]up|request a|no further|no action|needs? (a |an )?(review|attention)|before (deciding|releasing))\b/i;

function extractRecommendation(text) {
  const clean = stripMarkdown(text);
  if (!clean) return "";
  const sentences = (clean.match(/[^.!?]+[.!?]+(\s|$)/g) || [clean])
    .map((s) => s.trim())
    .filter(Boolean)
    .filter((s) => !RAW_DATA_SENTENCE.test(s) && s.split(",").length < 4);

  const actionable = sentences.filter((s) => RECOMMENDATION_SIGNAL.test(s));
  const chosen = actionable.slice(0, 3).join(" ").trim();
  if (!chosen) return "";
  return chosen.length > 320 ? `${chosen.slice(0, 317).trimEnd()}…` : chosen;
}

// Display-only grouping for "What happened" — collapses consecutive
// same-title timeline entries (e.g. repeated reminder pings) into one line
// with a count, so a noisy timeline doesn't read as a wall of near-duplicate
// text. Never touches the underlying data: Technical Details below still
// lists every raw timeline entry, unmodified and uncollapsed.
//
// Order-sheet titles are a special case, never shown with a raw "×N": the
// common cause of two consecutive "Order Sheet Uploaded" entries is a single
// upload logged twice by the backend (hearings.py's upload_document pushes a
// free-text "Order sheet uploaded: <file>" activity note, then immediately
// the hearing_completed -> verification_pending transition, which humanizes
// to the same title) — that's one real action, not a repeat, so it collapses
// to one clean business-level line with no count. Only when the group
// contains more than one genuine "Order sheet uploaded" note (uploadNoteCount
// > 1 — a real second/re-upload, not the transition's paired entry) does it
// read as an update instead.
const ORDER_SHEET_TITLES = new Set(["Order Sheet Uploaded", "Order Sheet Resubmitted", "Order Sheet Disputed"]);

function collapseConsecutiveEvents(events) {
  const collapsed = [];
  for (const e of events) {
    const isUploadNote = e.rawNote?.startsWith("Order sheet uploaded");
    const prev = collapsed[collapsed.length - 1];
    if (prev && prev.title === e.title) {
      prev.count += 1;
      prev.key = e.key;
      if (e.description) prev.description = e.description;
      if (isUploadNote) prev.uploadNoteCount += 1;
    } else {
      collapsed.push({ ...e, count: 1, uploadNoteCount: isUploadNote ? 1 : 0 });
    }
  }
  return collapsed.map((e) => {
    if (!ORDER_SHEET_TITLES.has(e.title)) return e;
    if (e.uploadNoteCount > 1) {
      return { ...e, title: "Order Sheet Updated", description: "The latest order sheet is awaiting verification.", count: 1 };
    }
    return { ...e, count: 1 };
  });
}

export default function OrderAgentHearingSummaryCard({ hearingId, open }) {
  const [aiSummary, setAiSummary] = useState(null);
  const [aiStatus, setAiStatus] = useState("idle"); // idle | loading | success | error — the AI REQUEST's
  // state, driven only by runAiSummary below. Never derived from hearing.status (verified/disputed/etc.)
  // in any way — those are two independent axes: what stage the hearing is in vs. whether an admin has
  // asked the AI to look at it, and if so, whether that specific ask succeeded.
  const [showDetails, setShowDetails] = useState(false);

  // This component instance is reused across hearings (the parent dialog never
  // unmounts it, just changes `hearingId`) — so a slow request for hearing A that's
  // still in flight when the admin switches to hearing B must not be allowed to land
  // on B and paint it "unavailable". requestIdRef is bumped on every hearing switch
  // and on every new click; a response is only applied if it's still the latest one.
  const requestIdRef = useRef(0);

  // Reset whenever the dialog opens for a (possibly different) hearing —
  // never carry a stale AI result over from the previously viewed hearing.
  useEffect(() => {
    requestIdRef.current += 1;
    setAiSummary(null);
    setAiStatus("idle");
    setShowDetails(false);
  }, [hearingId, open]);

  const runAiSummary = async () => {
    const myRequestId = ++requestIdRef.current;
    setAiStatus("loading");
    try {
      const data = await getOrderAgentHearingSummary(hearingId);
      if (requestIdRef.current !== myRequestId) return; // superseded by a hearing switch or a newer click
      setAiSummary(data);
      setAiStatus(data?.available ? "success" : "error");
    } catch {
      if (requestIdRef.current !== myRequestId) return;
      setAiSummary({ available: false, reason: "Request failed" });
      setAiStatus("error");
    }
  };

  const btn = AI_BUTTON_META[aiStatus];
  const BtnIcon = btn.icon;

  return (
    <div>
      <button type="button" onClick={runAiSummary} disabled={aiStatus === "loading"}
              className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide disabled:opacity-60 ${btn.className}`}>
        <BtnIcon className={`w-3.5 h-3.5 ${btn.spin ? "animate-spin" : ""}`} />
        {btn.label}
      </button>

      {aiSummary && (
        <HearingSummaryBody aiSummary={aiSummary} showDetails={showDetails} setShowDetails={setShowDetails} />
      )}
    </div>
  );
}

function HearingSummaryBody({ aiSummary, showDetails, setShowDetails }) {
  // Genuinely no data at all (e.g. hearing_id not found) — the "Summarize
  // with AI" button already reads "AI analysis unavailable" in this case, so
  // this line only needs to add the specific reason, never repeat that text.
  if (!aiSummary.available && !aiSummary.hearing) {
    return (
      <p className="text-sm mt-2 text-muted-foreground">{aiSummary.reason || "No data available for this hearing."}</p>
    );
  }

  const { hearing, escrow, documents, matching_session: matchingSession, summary } = aiSummary;
  const recommendation = aiSummary.available && summary ? extractRecommendation(summary) : "";
  const statusMeta = ORDER_STATUS_META[hearing?.status] || { icon: "ℹ️", label: hearing?.status?.replace(/_/g, " ") || "Unknown" };
  const attention = ATTENTION_META[computeAttentionLevel(hearing, matchingSession)];
  const amount = escrow?.amount ?? hearing?.fee;
  const orderSheet = documents?.find((d) => d.kind === "order_sheet");

  const recentEvents = collapseConsecutiveEvents(
    (hearing?.timeline || []).slice(-6).map((entry, i) => ({
      ...humanizeHearingActivity(entry, hearing), key: `${entry.status}-${entry.at}-${i}`, rawNote: entry.note || "",
    })),
  );

  return (
    <div className="mt-3 space-y-3 text-sm">
      {/* 1. Order status */}
      <div className="flex items-center gap-2">
        <span className="text-lg leading-none">{statusMeta.icon}</span>
        <span className="font-display font-bold">{statusMeta.label}</span>
      </div>

      {/* 2. Payment */}
      {(amount != null || escrow) && (
        <div className="rounded-md border bg-secondary/20 px-3 py-2 grid gap-1">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Amount</span>
            <span className="font-bold">{amount != null ? formatINR(amount) : "—"}</span>
          </div>
          {escrow && (
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Escrow status</span>
              <span className="font-semibold">{ESCROW_STATUS_LABEL[escrow.status] || escrow.status}</span>
            </div>
          )}
          {hearing?.status === "verification_pending" && hearing?.verification_pending_at && (
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Auto-release by</span>
              <span className="font-semibold">
                {(() => {
                  const d = new Date(hearing.verification_pending_at);
                  d.setDate(d.getDate() + AUTO_RELEASE_DELAY_DAYS);
                  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
                })()}
              </span>
            </div>
          )}
        </div>
      )}

      {/* 3. What happened */}
      {recentEvents.length > 0 && (
        <div>
          <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-1">What happened</div>
          <ul className="space-y-1 list-disc list-inside">
            {recentEvents.map((e) => (
              <li key={e.key}>
                <span className="font-semibold">{e.title}</span>
                {e.count > 1 ? <span className="text-muted-foreground"> ×{e.count}</span> : ""}
                {e.description ? ` — ${e.description}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 4. Attention required */}
      <div className="flex items-center gap-2">
        <span className="text-lg leading-none">{attention.icon}</span>
        <span className="font-semibold">{attention.label}</span>
      </div>

      {/* 5. Next action */}
      <div>
        <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-1">Next action</div>
        <p>{nextActionText(hearing, escrow)}</p>
      </div>

      {/* 6. AI recommendation — only ever shown once real AI output exists AND it actually
          contains a recommendation (see extractRecommendation above). When AI is unavailable,
          or the model's response has no actionable content to pull out, this section is simply
          omitted: the "Summarize with AI" button above is the one AI status indicator, and the
          system data in every section above is already fully valid on its own (it comes
          straight from the database, not the model), so no extra "unavailable"/"system note"
          messaging belongs here. */}
      {aiSummary.available && summary && recommendation && (
        <div>
          <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-1">AI recommendation</div>
          <p className="text-muted-foreground">{recommendation}</p>
        </div>
      )}

      {/* Technical details — collapsed by default */}
      <button type="button" onClick={() => setShowDetails((v) => !v)}
              className="flex items-center gap-1 text-2xs font-bold uppercase tracking-wide text-muted-foreground hover:text-foreground">
        {showDetails ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Technical details
      </button>
      {showDetails && (
        <div className="rounded-md border p-2.5 text-2xs text-muted-foreground space-y-1 font-mono">
          {hearing?.hearing_id && <div>Hearing ID: {hearing.hearing_id}</div>}
          {escrow?.escrow_id && <div>Escrow ID: {escrow.escrow_id}</div>}
          {hearing?.requesting_user_id && <div>Requesting user: {hearing.requesting_user_id}</div>}
          {hearing?.proxy_counsel_user_id && <div>Proxy counsel: {hearing.proxy_counsel_user_id}</div>}
          {matchingSession?.status && <div>Matching session status: {matchingSession.status}</div>}
          {orderSheet && <div>Order sheet file: {orderSheet.original_filename}</div>}
          {(hearing?.timeline || []).map((e, i) => (
            <div key={i}>{new Date(e.at).toLocaleString("en-IN")} — {e.note || e.status}</div>
          ))}
        </div>
      )}
    </div>
  );
}
