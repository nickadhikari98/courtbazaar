import React, { useEffect, useRef, useState } from "react";
import { api, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Send, Loader2, Scale, User, RefreshCw } from "lucide-react";

// Multi-turn conversation via POST /ai/chat. Backend routing (ai_chat.py)
// transparently grounds some replies in live public CourtBazaar data
// (courts/states/services/Proxy Counsel search) — this component has no
// knowledge of that; it only ever renders whatever `reply` string comes
// back. Landing-page-only by product decision: personal order/hearing data
// is intentionally never surfaced through this widget (see ai_chat.py's
// ORDERS_UNAVAILABLE_MESSAGE/HEARINGS_UNAVAILABLE_MESSAGE).
//
// Controlled panel: the trigger (a real input + button) lives inline in
// HeroSection's normal document flow, but this panel is always `fixed` to
// the screen's right corner and only rendered at all when `open` is true —
// it never occupies document flow and never pushes/reflows Core Services or
// any other section, regardless of where in the tree it's mounted.
const UNAVAILABLE_TEXT = "Instant Legal Help isn't available right now. Please try again later.";
const GENERIC_ERROR_TEXT = "Sorry — I'm having trouble responding right now. Please try again in a moment.";

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

function cleanAssistantText(str) {
  if (!str) return str;
  let cleaned = decodeEntitiesUntilStable(str);
  cleaned = cleaned.replace(/ /g, " "); // non-breaking space -> normal space
  // Backslash-unescape BEFORE stripping bold/italic, so "\*\*bold\*\*" first
  // becomes "**bold**" and is then caught below too.
  cleaned = cleaned.replace(/\\([-*_#.>+![\]()~`\\])/g, "$1");
  cleaned = cleaned.replace(/\*\*(.+?)\*\*/g, "$1");
  cleaned = cleaned.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "$1");
  cleaned = cleaned.replace(/^\s{0,3}#{1,6}\s+/gm, "");
  cleaned = cleaned.replace(/^[ \t]*-[ \t]+/gm, "• "); // "- item" -> "• item"
  cleaned = cleaned.replace(/[ \t]{2,}/g, " ");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

const SESSION_EXPIRED_TEXT = "This chat session is no longer available. Please send your message again to start a new chat.";

export default function InstantLegalHelpWidget({ open, onClose, initialMessage }) {
  const [conversationId, setConversationId] = useState(null);
  // Secret the backend issues with an anonymous conversation's first reply;
  // it must be sent back to continue that conversation (the id alone isn't
  // enough). Kept in memory only, like conversationId.
  const [conversationToken, setConversationToken] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const prevOpenRef = useRef(false);
  // Bumped on every "New chat" so an in-flight request from the conversation
  // just cleared can never land its reply into the fresh, empty one.
  const sessionRef = useRef(0);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, open]);

  const send = async (text) => {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    const mySession = sessionRef.current;
    setMsgs((prev) => [...prev, { role: "user", text: content }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", {
        conversation_id: conversationId,
        message: content,
        ...(conversationToken ? { conversation_token: conversationToken } : {}),
      });
      if (sessionRef.current !== mySession) return; // superseded by "New chat" while this was in flight
      if (data?.conversation_id) setConversationId(data.conversation_id);
      if (data?.conversation_token) setConversationToken(data.conversation_token);
      setMsgs((prev) => [...prev, { role: "assistant", text: data?.reply || GENERIC_ERROR_TEXT, sources: data?.sources || [] }]);
    } catch (err) {
      if (sessionRef.current !== mySession) return;
      if (err?.response?.status === 404) {
        // The conversation can't be continued (unknown or not ours) — start fresh next time.
        setConversationId(null);
        setConversationToken(null);
        setMsgs((prev) => [...prev, { role: "assistant", text: SESSION_EXPIRED_TEXT }]);
        return;
      }
      const isUnavailable = err?.response?.status === 503;
      setMsgs((prev) => [...prev, { role: "assistant", text: isUnavailable ? UNAVAILABLE_TEXT : GENERIC_ERROR_TEXT }]);
      if (!isUnavailable) toast.error(getErrorMessage(err, "Something went wrong. Please try again."));
    } finally {
      if (sessionRef.current === mySession) setLoading(false);
    }
  };

  // Carries text typed into the landing-page trigger (HeroSection) straight
  // into the first chat message — fires exactly once per open transition
  // (false -> true), never again while the panel stays open, so it can't
  // resend on unrelated re-renders.
  useEffect(() => {
    if (open && !prevOpenRef.current && initialMessage) {
      send(initialMessage);
    }
    prevOpenRef.current = open;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialMessage]);

  const handleNewChat = () => {
    sessionRef.current += 1;
    setMsgs([]);
    setConversationId(null);
    setConversationToken(null);
    setInput("");
    setLoading(false);
  };

  if (!open) return null;

  return (
    <div
      className="fixed bottom-5 right-5 z-50 w-[min(380px,calc(100vw-2.5rem))] h-[min(560px,calc(100vh-6rem))] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden"
      data-testid="instant-legal-help-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-primary text-white shrink-0">
        <div>
          <div className="font-display font-bold text-sm">Instant Legal Help</div>
          <div className="text-xs text-white/80">Public legal guidance</div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleNewChat}
            aria-label="Start a new chat"
            title="Start a new chat"
            data-testid="instant-legal-help-new-chat"
            className="text-white/80 hover:text-white w-6 h-6 flex items-center justify-center"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            aria-label="Close chat"
            data-testid="instant-legal-help-close"
            className="text-2xl leading-none text-white/80 hover:text-white w-6 h-6 flex items-center justify-center"
          >
            ×
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto cb-scroll p-4 space-y-4" data-testid="instant-legal-help-messages">
        {msgs.length === 0 && (
          <div className="text-center py-8 px-2">
            <div className="w-12 h-12 mx-auto bg-accent/10 rounded-2xl flex items-center justify-center mb-3">
              <Scale className="w-6 h-6 text-accent" />
            </div>
            <p className="text-sm font-semibold">Tell me what's going on and I'll help you figure out the next step.</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`} data-testid={`instant-legal-help-msg-${m.role}-${i}`}>
            <div className={`w-7 h-7 rounded-lg shrink-0 flex items-center justify-center ${m.role === "user" ? "bg-primary text-white" : "bg-accent text-white"}`}>
              {m.role === "user" ? <User className="w-3.5 h-3.5" /> : <Scale className="w-3.5 h-3.5" />}
            </div>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap break-words leading-6 ${m.role === "user" ? "bg-primary text-white" : "bg-secondary text-foreground"}`}>
              {m.role === "assistant" ? cleanAssistantText(m.text) : m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-2" data-testid="instant-legal-help-loading">
            <div className="w-7 h-7 rounded-lg bg-accent text-white flex items-center justify-center"><Scale className="w-3.5 h-3.5" /></div>
            <div className="bg-secondary rounded-2xl px-3.5 py-2.5 flex gap-1.5">
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-border p-3 flex gap-2 shrink-0">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Describe your situation, legal issue, or service need..."
          className="flex-1"
          disabled={loading}
          data-testid="instant-legal-help-input"
        />
        <Button onClick={() => send()} disabled={loading || !input.trim()} className="bg-accent hover:bg-accent/90 font-bold px-4" data-testid="instant-legal-help-send">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </Button>
      </div>
    </div>
  );
}
