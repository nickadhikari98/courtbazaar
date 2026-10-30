import React from "react";
import { BookOpen, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import ChatMarkdown from "./ChatMarkdown";

/* A document answer as one card: summary, then one row per point. The server
   builds `answer` from text that passed the evidence checks
   (answer_guard.validate_answer_card), and each point's `cite` numbers are
   positions in the Sources list below the card. Shape is still checked here:
   anything unexpected makes normalizeAnswer return null, and the page falls
   back to rendering the plain `reply`. */

const ICONS = { rule: BookOpen, check: CheckCircle2, warning: TriangleAlert, info: Info };
const ICON_TONES = { success: "text-emerald-600", warning: "text-amber-600", neutral: "text-accent" };
const BADGE_TONES = {
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warning: "bg-amber-50 text-amber-800 border-amber-200",
  neutral: "bg-slate-100 text-slate-600 border-slate-200",
};
const text = (value) => (typeof value === "string" ? value.trim() : "");

/* Exported for tests. */
export function normalizeAnswer(raw) {
  const summary = text(raw?.summary);
  if (!summary || !Array.isArray(raw?.points)) return null;
  const points = raw.points
    .filter((p) => p && text(p.title) && text(p.text))
    .map((p) => ({
      icon: ICONS[p.icon] ? p.icon : "info",
      tone: BADGE_TONES[p.tone] ? p.tone : "neutral",
      title: text(p.title),
      badge: text(p.badge),
      text: text(p.text),
      cite: Array.isArray(p.cite) ? p.cite.filter(Number.isInteger) : [],
    }));
  if (!points.length) return null;
  return {
    partial: raw.status === "partial",
    summary,
    points,
    followUp: text(raw.follow_up),
    note: text(raw.note),
    noteDetail: text(raw.note_detail),
  };
}

/* The disclaimer under a document answer, card or plain. */
export function AnswerNote({ note, detail, clean }) {
  if (!note) return null;
  return (
    <div className="flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">
      <p data-testid="instant-legal-help-answer-note">{clean(note)}</p>
      {detail && (
        // A popover, not a tooltip: it has to open on a phone too.
        <Popover>
          <PopoverTrigger
            aria-label="More about this answer"
            className="mt-0.5 shrink-0 rounded-full hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            data-testid="instant-legal-help-note-info"
          >
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
          </PopoverTrigger>
          <PopoverContent className="w-72 text-xs leading-5" data-testid="instant-legal-help-note-detail">
            {clean(detail)}
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

export default function AnswerCard({ answer, citeLinks, clean }) {
  return (
    <div className="space-y-3">
      <article className="rounded-2xl border border-border bg-white shadow-sm overflow-hidden" data-testid="instant-legal-help-answer-card">
        {answer.partial && (
          <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs leading-5 text-amber-800" data-testid="instant-legal-help-partial-note">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>Partial answer: only part of this is covered by the available documents.</span>
          </div>
        )}
        <div className="px-4 py-3.5 font-medium">
          <ChatMarkdown text={clean(answer.summary)} citeLinks={citeLinks} />
        </div>
        <ul className="divide-y divide-border border-t border-border">
          {answer.points.map((point, i) => {
            const Icon = ICONS[point.icon];
            const chips = point.cite.filter((n) => citeLinks.has(n)).map((n) => `[${n}]`).join(" ");
            return (
              <li key={`${i}-${point.title}`} className="flex gap-3 px-4 py-3" data-testid="instant-legal-help-answer-point">
                <Icon className={`mt-1 h-4 w-4 shrink-0 ${ICON_TONES[point.tone]}`} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <h4 className="min-w-0 flex-1 text-[15px] font-semibold leading-6 text-foreground [overflow-wrap:anywhere]">{clean(point.title)}</h4>
                    {point.badge && (
                      <span className={`shrink-0 whitespace-nowrap rounded-full border px-2 py-0.5 text-2xs font-semibold ${BADGE_TONES[point.tone]}`}>
                        {clean(point.badge)}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 text-muted-foreground">
                    <ChatMarkdown text={clean(`${point.text} ${chips}`)} citeLinks={citeLinks} />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
        {answer.followUp && (
          <p className="border-t border-border bg-accent/5 px-4 py-2.5 text-sm leading-6 text-foreground">{clean(answer.followUp)}</p>
        )}
      </article>
      <AnswerNote note={answer.note} detail={answer.noteDetail} clean={clean} />
    </div>
  );
}
