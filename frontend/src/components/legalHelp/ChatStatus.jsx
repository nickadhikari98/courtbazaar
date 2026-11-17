import React, { useEffect, useState } from "react";
import { Check, Loader2, Scale } from "lucide-react";

/* What the chat shows while an answer is on its way: one bordered panel with
   the server's steps (ai_chat.stream_chat_events sends each when the pipeline
   really reaches it; only the first is set here, as the page knows it has
   started), then skeleton bars while the card is written and verified. The
   page swaps the whole panel for the finished answer. Mounted for one
   request, so the timer runs from send to answer. */

export const FIRST_STEP = { step: "understanding", text: "Understanding your question…" };

// Writing is covered by the skeleton, not a row of its own.
const CARD_STEPS = ["writing", "verifying"];

/* Exported for tests: a step's line, past tense (no "…") once it is done. */
export function stepLabel(step, done) {
  if (step.step === "verifying") return done ? "Verified citations" : "Verifying citations…";
  if (!done) return String(step.text || "");
  const text = String(step.text || "").replace(/…$/, "");
  if (step.step === "searching") return text.replace(/^Searching\b/, "Searched");
  if (step.step === "understanding") return text.replace(/^Understanding\b/, "Understood");
  return text;
}

/* Our own feather mark, drawn here, in the brand ochre (text-accent). It
   bobs while the answer is written and is still under reduced motion; it
   unmounts with this panel the moment the answer renders. */
export function WritingQuill({ className = "" }) {
  return (
    <svg
      viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"
      className={`text-accent origin-bottom-left motion-safe:animate-quill ${className}`}
      data-testid="instant-legal-help-quill"
    >
      <path d="M20 3C13 4 8 9 6 16l-1 4 4-1c7-2 11-7 11-16Z" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M5 20 15 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export default function ChatStatus({ steps }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const all = steps.length ? steps : [FIRST_STEP];
  const current = all[all.length - 1];
  const shown = all.filter((s) => s.step !== "writing");
  return (
    <div className="flex items-start gap-3" data-testid="instant-legal-help-loading">
      <div className="relative shrink-0" aria-hidden="true">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white"><Scale className="h-4 w-4" /></div>
        <WritingQuill className="absolute -right-2.5 -top-2" />
      </div>
    <div className="min-w-0 flex-1 rounded-2xl border border-border bg-white p-4">
      <ul className="space-y-1.5 text-sm" data-testid="instant-legal-help-status-steps">
        {shown.map((s, i) => {
          const done = s !== current;
          return (
            <li key={`${i}-${s.step}`} className={`flex items-start gap-2 ${done ? "text-muted-foreground" : "text-foreground"}`}>
              {done
                ? <Check className="mt-1 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
                : <Loader2 className="mt-1 h-3.5 w-3.5 shrink-0 motion-safe:animate-spin text-accent" aria-hidden="true" />}
              <span
                className="min-w-0 flex-1 [overflow-wrap:anywhere]"
                {...(done ? {} : { role: "status", "data-testid": "instant-legal-help-status-text" })}
              >
                {stepLabel(s, done)}
              </span>
              {/* Hidden under 1s so instant replies (greetings) never flash a "0s" timer. */}
              {!done && seconds > 0 && <span className="shrink-0 tabular-nums text-xs text-muted-foreground" aria-hidden="true" data-testid="instant-legal-help-status-timer">{seconds}s</span>}
            </li>
          );
        })}
      </ul>
      {CARD_STEPS.includes(current.step) && (
        <div className="mt-4 space-y-2" data-testid="instant-legal-help-skeleton">
          {["w-full", "w-11/12", "w-2/3"].map((w) => <div key={w} className={`h-3 ${w} rounded bg-slate-200 motion-safe:animate-pulse`} />)}
          <p className="pt-1 text-xs text-muted-foreground">The full answer card appears here once it is verified.</p>
        </div>
      )}
    </div>
    </div>
  );
}
