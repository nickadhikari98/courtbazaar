import React, { useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowUp, Loader2, Scale, User, SquarePen, Landmark, FileText, Users, Info, RotateCcw } from "lucide-react";
import ChatStatus, { FIRST_STEP } from "./ChatStatus";
import { streamChat } from "./chatStream";
import ChatMarkdown from "./ChatMarkdown";
import ChatSources, { documentCitationLinks, webCitationLinks } from "./ChatSources";
import AnswerCard, { AnswerNote, normalizeAnswer } from "./AnswerCard";

// Multi-turn conversation via POST /ai/chat/stream. Backend routing (ai_chat.py)
// transparently grounds some replies in live public CourtBazaar data
// (courts/states/services/Proxy Counsel search) — this component has no
// knowledge of that; it only ever renders whatever `reply` string comes
// back. Public guidance only by product decision: personal order/hearing
// data is intentionally never surfaced through this chat (see ai_chat.py's
// ORDERS_UNAVAILABLE_MESSAGE/HEARINGS_UNAVAILABLE_MESSAGE).
//
// Fills whatever box it's mounted in (h-full, flex column): header, a
// scrolling conversation, and a composer pinned to the bottom. Mounted by
// the dedicated /legal-help page (pages/marketing/LegalHelp.jsx), which the
// landing page's "Chat with Instant Legal Help" launcher opens — it used to
// be a small fixed corner panel on the landing page itself.
const UNAVAILABLE_TEXT = "Instant Legal Help isn't available right now. Please try again later.";
const GENERIC_ERROR_TEXT = "Sorry — I'm having trouble responding right now. Please try again in a moment.";
const TIMEOUT_TEXT = "This is taking longer than expected. Please try again.";
// Longest silence on the stream, not the whole request: every status event
// resets it, so a slow answer that's progressing is never cut off.
const CHAT_TIMEOUT_MS = 60000;

// UX-polish defense in depth: the backend already strips Markdown syntax and
// decodes HTML entities before a reply is ever stored (see ai_chat.py's
// _sanitize_reply, which this mirrors exactly) — this is the client-side
// safety net for whatever slips through anyway (a stale cached reply, a
// future provider quirk), so the UI never shows raw "**bold**"/"&#x20;"/
// "\-"-style artifacts regardless of what the API actually returned. Never
// applied to the user's own typed text. Never uses dangerouslySetInnerHTML —
// the textarea trick below only reads back decoded text, nothing is ever
// re-inserted into the live DOM as markup.
//
// Root-caused two artifacts that survived a naive single-pass version
// (mirrors the backend investigation): setting el.innerHTML and reading
// el.value only decodes ONE layer of encoding, so a DOUBLE-encoded entity
// like "&amp;#x20;" (the "&" itself was escaped before the numeric
// reference was appended) only resolves as far as the still-visible
// "&#x20;" after one pass — a second pass is needed to reach a real space.
// And "\-"/"1\." are backslash-escaped Markdown punctuation, not HTML
// entities at all, so the textarea decode trick never touches them.
function decodeHtmlEntitiesOnce(str) {
  if (!str) return str;
  const el = document.createElement("textarea");
  el.innerHTML = str;
  return el.value;
}

function decodeEntitiesUntilStable(str, maxPasses = 4) {
  let cleaned = str;
  for (let i = 0; i < maxPasses; i++) {
    const next = decodeHtmlEntitiesOnce(cleaned);
    if (next === cleaned) break;
    cleaned = next;
  }
  return cleaned;
}

// Keeps the Markdown subset ChatMarkdown renders (## / ### headings, lists,
// **bold**) and removes everything else that could show up as raw syntax:
// entities, backslash escapes, single-asterisk italics, deeper headings.
export function cleanAssistantText(str) {
  if (!str) return str;
  let cleaned = decodeEntitiesUntilStable(str);
  cleaned = cleaned.replace(/\u00a0/g, " "); // non-breaking space -> normal space
  cleaned = cleaned.replace(/\\([-*_#.>+![\]()~`\\])/g, "$1");
  cleaned = cleaned.replace(/(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)/g, "$1");
  cleaned = cleaned.replace(/^\s{0,3}#{4,6}\s+/gm, "### ");
  cleaned = cleaned.replace(/^\s{0,3}#\s+/gm, "## ");
  cleaned = cleaned.replace(/[ \t]{2,}/g, " ");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

const GROUNDING_STATES = ["supported", "partial", "insufficient"];

/* What one /ai/chat response becomes in the transcript. The response comes
   from our own API, but its shape is still checked so a malformed or
   unexpected body degrades to the generic error text instead of a crash or a
   blank bubble. Citations are validated again by ChatSources. */
export function assistantMessageFrom(data) {
  const reply = typeof data?.reply === "string" && data.reply.trim() ? data.reply : GENERIC_ERROR_TEXT;
  const body = typeof data?.body === "string" && data.body.trim() ? data.body : null;
  return {
    role: "assistant",
    text: body ?? reply, // `body` is the reply without the note shown under it
    note: body && typeof data?.note === "string" ? data.note : null,
    noteDetail: body && typeof data?.note_detail === "string" ? data.note_detail : null,
    citations: Array.isArray(data?.citations) ? data.citations : [],
    grounding: GROUNDING_STATES.includes(data?.grounding) ? data.grounding : null,
    answer: normalizeAnswer(data?.answer),
  };
}

const SESSION_EXPIRED_TEXT = "This chat session is no longer available. Please send your message again to start a new chat.";

// What the empty state says the chat is for. Descriptive only, not
// clickable prompts.
const HELP_TOPICS = [
  { icon: Scale, title: "Understand your situation", text: "Plain-language guidance on legal processes and what to do next." },
  { icon: FileText, title: "Find the right service", text: "E-filing, printing, scanning and the other court work we handle." },
  { icon: Users, title: "Get court support", text: "When a proxy counsel or advocate can help, and how to hire one." },
];

export default function InstantLegalHelpChat({ initialMessage }) {
  const [conversationId, setConversationId] = useState(null);
  // Secret the backend issues with an anonymous conversation's first reply;
  // it must be sent back to continue that conversation (the id alone isn't
  // enough). Kept in memory only, like conversationId.
  const [conversationToken, setConversationToken] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const initialSentRef = useRef(false);
  // Bumped on every "New chat" so an in-flight request from the conversation
  // just cleared can never land its reply into the fresh, empty one.
  const sessionRef = useRef(0);
  const abortRef = useRef(null);

  // Leaving the page cancels the request so nothing lands (or toasts) after unmount.
  useEffect(() => () => {
    sessionRef.current += 1;
    abortRef.current?.abort();
  }, []);

  // Scroll the conversation box itself, not the page: scrollIntoView would
  // also move the window on a full-height layout. While waiting, show the
  // latest question and "Thinking…" (the bottom). When a reply lands, scroll
  // to its question so a long answer reads from the top instead of opening
  // at its Sources. The empty state stays at the top so its heading is
  // visible on phones.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let top = 0;
    if (loading) {
      top = el.scrollHeight;
    } else if (msgs.length) {
      const questions = el.querySelectorAll('[data-testid^="instant-legal-help-msg-user-"]');
      const last = questions[questions.length - 1];
      top = last ? last.offsetTop - 16 : el.scrollHeight;
    }
    top = Math.max(0, Math.min(top, el.scrollHeight - el.clientHeight));
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (typeof el.scrollTo === "function") el.scrollTo({ top, behavior: reduceMotion ? "auto" : "smooth" });
    else el.scrollTop = top;
  }, [msgs, loading]);

  // Grow the composer with its content, up to max-h (then it scrolls).
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  const send = async (text) => {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    const mySession = sessionRef.current;
    setMsgs((prev) => [...prev, { role: "user", text: content }]);
    setInput("");
    setLoading(true);
    setSteps([FIRST_STEP]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await streamChat({
        conversation_id: conversationId,
        message: content,
        ...(conversationToken ? { conversation_token: conversationToken } : {}),
      }, {
        idleMs: CHAT_TIMEOUT_MS,
        signal: controller.signal,
        onStatus: (event) => {
          if (sessionRef.current !== mySession) return;
          // A step can update its text ("Searching…" twice): one row each.
          setSteps((prev) => (prev[prev.length - 1]?.step === event.step
            ? [...prev.slice(0, -1), event] : [...prev, event]));
        },
      });
      if (sessionRef.current !== mySession) return; // superseded by "New chat" while this was in flight
      if (typeof data?.conversation_id === "string" && data.conversation_id) setConversationId(data.conversation_id);
      if (typeof data?.conversation_token === "string" && data.conversation_token) setConversationToken(data.conversation_token);
      setMsgs((prev) => [...prev, assistantMessageFrom(data)]);
    } catch (err) {
      if (sessionRef.current !== mySession) return;
      if (err?.response?.status === 404) {
        // The conversation can't be continued (unknown or not ours) — start fresh next time.
        setConversationId(null);
        setConversationToken(null);
        setMsgs((prev) => [...prev, { role: "assistant", text: SESSION_EXPIRED_TEXT, retryText: content }]);
        return;
      }
      // `retryText` keeps the user's question so "Try again" can resend it as-is.
      if (err?.code === "ECONNABORTED") {
        setMsgs((prev) => [...prev, { role: "assistant", text: TIMEOUT_TEXT, retryText: content }]);
        return;
      }
      const isUnavailable = err?.response?.status === 503;
      setMsgs((prev) => [...prev, { role: "assistant", text: isUnavailable ? UNAVAILABLE_TEXT : GENERIC_ERROR_TEXT, retryText: content }]);
      if (!isUnavailable) toast.error(getErrorMessage(err, "Something went wrong. Please try again."));
    } finally {
      if (sessionRef.current === mySession) setLoading(false);
    }
  };

  // Text typed into the landing-page launcher (HeroSection) becomes the
  // first message — sent exactly once per mount, never again on re-renders.
  useEffect(() => {
    if (initialMessage && !initialSentRef.current) {
      initialSentRef.current = true;
      send(initialMessage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessage]);

  // Replaces the failed exchange (question + error) with a fresh attempt.
  const retry = (text) => {
    setMsgs((prev) => prev.slice(0, -2));
    send(text);
  };

  const handleNewChat = () => {
    sessionRef.current += 1;
    abortRef.current?.abort();
    setMsgs([]);
    setConversationId(null);
    setConversationToken(null);
    setInput("");
    setLoading(false);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    // Enter sends, Shift+Enter is a new line; never send mid-IME-composition.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col flex-1 h-full min-h-0 bg-background" data-testid="instant-legal-help-panel">
      <div className="border-b border-border bg-white shrink-0">
        <div className="max-w-3xl mx-auto w-full px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
              <Scale className="w-[18px] h-[18px] text-accent" />
            </div>
            <div className="min-w-0">
              <h1 className="font-display font-bold text-base leading-tight">Instant Legal Help</h1>
              <p className="text-xs text-muted-foreground truncate">Public legal guidance from CourtBazaar</p>
            </div>
          </div>
          <Button
            type="button" variant="outline" size="sm" onClick={handleNewChat}
            disabled={msgs.length === 0 && !loading}
            aria-label="Start a new chat" title="Start a new chat"
            className="shrink-0 font-semibold"
            data-testid="instant-legal-help-new-chat"
          >
            <SquarePen className="w-4 h-4 sm:mr-1.5" />
            <span className="hidden sm:inline">New chat</span>
          </Button>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="relative flex-1 min-h-0 overflow-y-auto overscroll-contain cb-scroll"
        role="log" aria-live="polite" aria-label="Conversation"
        data-testid="instant-legal-help-messages"
      >
        <div className="max-w-3xl mx-auto w-full px-4 py-6 sm:py-8 space-y-6">
          {msgs.length === 0 && !loading && (
            <div className="py-6 sm:py-12 text-center" data-testid="instant-legal-help-empty">
              <div className="w-14 h-14 mx-auto bg-accent/10 rounded-2xl flex items-center justify-center mb-4">
                <Landmark className="w-7 h-7 text-accent" />
              </div>
              <h2 className="font-display font-bold text-xl sm:text-2xl">How can we help today?</h2>
              <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-6">
                Tell me what's going on and I'll help you figure out the next step.
              </p>
              <div className="grid sm:grid-cols-3 gap-3 mt-8 text-left">
                {HELP_TOPICS.map(({ icon: Icon, title, text }) => (
                  <div key={title} className="rounded-xl border border-border bg-white p-4">
                    <Icon className="w-4 h-4 text-accent mb-2" />
                    <div className="text-sm font-semibold">{title}</div>
                    <p className="text-xs text-muted-foreground mt-1 leading-5">{text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (m.role === "user" ? (
            <div key={i} className="flex justify-end gap-3" data-testid={`instant-legal-help-msg-user-${i}`}>
              <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-br-md bg-primary text-white px-4 py-2.5 text-[15px] leading-7 whitespace-pre-wrap break-words">
                {m.text}
              </div>
              <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary shrink-0 hidden sm:flex items-center justify-center" aria-hidden="true">
                <User className="w-4 h-4" />
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-3 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300" data-testid={`instant-legal-help-msg-assistant-${i}`}>
              <div className="w-8 h-8 rounded-lg bg-accent text-white shrink-0 flex items-center justify-center" aria-hidden="true">
                <Scale className="w-4 h-4" />
              </div>
              <div className="min-w-0 flex-1 pt-0.5">
                {m.grounding === "insufficient" ? (
                  // Not a failure: the approved documents just don't cover it.
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 flex gap-3" data-testid="instant-legal-help-insufficient">
                    <Info className="w-4 h-4 text-amber-700 shrink-0 mt-1" aria-hidden="true" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-amber-800 uppercase tracking-wide">Not covered by the available documents</div>
                      <div className="mt-1"><ChatMarkdown text={cleanAssistantText(m.text)} citeLinks={webCitationLinks(m.citations)} /></div>
                    </div>
                  </div>
                ) : m.answer ? (
                  <AnswerCard answer={m.answer} citeLinks={documentCitationLinks(m.citations)} clean={cleanAssistantText} />
                ) : (
                  <div className="space-y-3">
                    <ChatMarkdown text={cleanAssistantText(m.text)} citeLinks={webCitationLinks(m.citations)} />
                    <AnswerNote note={m.note} detail={m.noteDetail} clean={cleanAssistantText} />
                  </div>
                )}
                <ChatSources citations={m.citations} />
                {m.retryText && i === msgs.length - 1 && !loading && (
                  <Button
                    type="button" variant="outline" size="sm" onClick={() => retry(m.retryText)}
                    className="mt-3 font-semibold" data-testid="instant-legal-help-retry"
                  >
                    <RotateCcw className="w-4 h-4 mr-1.5" />Try again
                  </Button>
                )}
              </div>
            </div>
          )))}
          {loading && <ChatStatus steps={steps} />}
        </div>
      </div>

      <div className="shrink-0 bg-background pb-[max(env(safe-area-inset-bottom),0.75rem)]">
        <div className="max-w-3xl mx-auto w-full px-4 pt-2">
          <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm focus-within:border-accent/60 focus-within:ring-2 focus-within:ring-accent/20 transition-shadow">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your situation, legal issue, or service need..."
              aria-label="Message Instant Legal Help"
              autoFocus
              className="flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 max-h-40 overflow-y-auto cb-scroll placeholder:text-slate-400 focus:outline-none"
              data-testid="instant-legal-help-input"
            />
            <Button
              type="button" onClick={() => send()} disabled={loading || !input.trim()}
              aria-label="Send message"
              className="h-10 w-10 shrink-0 rounded-xl bg-accent p-0 hover:bg-accent/90"
              data-testid="instant-legal-help-send"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUp className="w-5 h-5" />}
            </Button>
          </div>
          <p className="text-2xs text-muted-foreground text-center mt-2 px-2">
            General guidance only, not a substitute for advice from a lawyer on your specific case.
          </p>
        </div>
      </div>
    </div>
  );
}
