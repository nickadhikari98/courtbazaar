import React, { useEffect, useState } from "react";
import { Check, ChevronDown, Scale } from "lucide-react";

/* What the chat shows while an answer is on its way. Every step comes from
   the server (ai_chat.stream_chat_events), which sends one when the pipeline
   really reaches it; only the first is set here, as the page knows it has
   started. Mounted for one request, so the timer runs from send to answer. */

export const FIRST_STEP = { step: "understanding", text: "Understanding your question…" };

export default function ChatStatus({ steps }) {
  const [seconds, setSeconds] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const current = steps[steps.length - 1] ?? FIRST_STEP;
  const done = steps.slice(0, -1);
  return (
    <div className="flex gap-3 items-start" data-testid="instant-legal-help-loading">
      <div className="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center shrink-0" aria-hidden="true">
        <Scale className="w-4 h-4" />
      </div>
      <div className="min-w-0 flex-1 pt-1.5 text-sm text-muted-foreground">
        <div className="flex items-center gap-2.5">
          <span className="flex gap-1 items-center shrink-0" aria-hidden="true">
            <span className="w-1.5 h-1.5 bg-accent rounded-full motion-safe:animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-1.5 h-1.5 bg-accent rounded-full motion-safe:animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-1.5 h-1.5 bg-accent rounded-full motion-safe:animate-bounce" style={{ animationDelay: "300ms" }} />
          </span>
          {/* Keyed so each new step fades in. */}
          <span key={current.text} role="status" className="min-w-0 [overflow-wrap:anywhere] motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200" data-testid="instant-legal-help-status-text">
            {current.text}
          </span>
          {/* Hidden under 1s so instant replies (greetings) never flash a "0s" timer. */}
          {seconds > 0 && <span className="shrink-0 tabular-nums text-xs text-muted-foreground/80" aria-hidden="true" data-testid="instant-legal-help-status-timer">{seconds}s</span>}
          {done.length > 0 && (
            <button
              type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="Show completed steps"
              className="shrink-0 rounded p-0.5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
              data-testid="instant-legal-help-status-toggle"
            >
              <ChevronDown className={`h-4 w-4 motion-safe:transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
            </button>
          )}
        </div>
        {open && done.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs" data-testid="instant-legal-help-status-steps">
            {done.map((s, i) => (
              <li key={`${i}-${s.step}`} className="flex items-start gap-1.5">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" aria-hidden="true" />
                <span className="min-w-0 [overflow-wrap:anywhere]">{s.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
