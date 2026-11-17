import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, getErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowUp, Scale, User, Info, RotateCcw, Menu, Paperclip, Square, Copy, Search, SquarePen } from "lucide-react";
import ChatSidebar from "./ChatSidebar";
import ChatPalette from "./ChatPalette";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import SupportTicketModal from "@/components/legal/SupportTicketModal";
import { Link } from "react-router-dom";
import SettingsDialog from "./SettingsDialog";
import { formatUsage } from "./usage";
import ChatStatus, { FIRST_STEP } from "./ChatStatus";
import { streamChat } from "./chatStream";
import ChatMarkdown from "./ChatMarkdown";
import ChatSources, { documentCitationLinks, webCitationLinks } from "./ChatSources";
import AnswerCard, { AnswerNote, answerPlainText, normalizeAnswer } from "./AnswerCard";

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

// Actions only on real answers: ones with sources, or longer than a one-line reply.
const ACTIONS_MIN_CHARS = 200;
export const hasActions = (m) => !m.retryText
  && ((Array.isArray(m.citations) && m.citations.length > 0) || (m.text || "").length > ACTIONS_MIN_CHARS);

// A daily limit (chat_usage) refused the message: which card to show.
const LIMIT_ACTIONS = {
  guest: { to: "/register", label: "Sign up to continue" },
  free: { to: "/subscription", label: "Upgrade" },
  paid: null,
};

function LimitCard({ reason, text }) {
  const action = LIMIT_ACTIONS[reason];
  return (
    <div className="rounded-xl border border-accent/40 bg-accent/5 px-4 py-3" data-testid="instant-legal-help-limit">
      <p className="text-sm leading-6">{text}</p>
      {action && (
        <Link to={action.to} className="mt-2 inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent/90"
          data-testid="instant-legal-help-limit-action">
          {action.label}
        </Link>
      )}
    </div>
  );
}

const STOPPED_TEXT = "Stopped. The answer was not generated.";
const SESSION_EXPIRED_TEXT = "This chat session is no longer available. Please send your message again to start a new chat.";

// Welcome-screen cards; clicking one sends its text as the first message.
const SUGGESTIONS = [
  "I received a cheque bounce notice. What should I do?",
  "How do I e-file a case in the Delhi High Court?",
  "When should I hire a proxy counsel for a hearing?",
  "What is the difference between arbitration and mediation?",
];

const MODE_KEY = "instantLegalHelpMode";
const MODES = [{ value: "layman", label: "Layman" }, { value: "lawyer", label: "Lawyer" }];

function savedMode() {
  try {
    return localStorage.getItem(MODE_KEY) === "lawyer" ? "lawyer" : "layman";
  } catch {
    return "layman"; // storage blocked: default
  }
}

export default function InstantLegalHelpChat({ initialMessage, fullScreen = false }) {
  const chatId = useId(); // prefixes each answer's source-row ids, so a chip jumps to its own message's row
  const [mode, setMode] = useState(savedMode);
  const [conversationId, setConversationId] = useState(null);
  // Secret the backend issues with an anonymous conversation's first reply;
  // it must be sent back to continue that conversation (the id alone isn't
  // enough). Kept in memory only, like conversationId.
  const [conversationToken, setConversationToken] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const auth = useAuth();
  const user = auth?.user || null;
  const [usage, setUsage] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [chats, setChats] = useState([]);
  const [archivedChats, setArchivedChats] = useState([]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // the chat awaiting delete confirmation
  const [deleting, setDeleting] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const scrollRef = useRef(null);
  const chooseMode = (value) => {
    setMode(value);
    try { localStorage.setItem(MODE_KEY, value); } catch { /* not remembered; still applies now */ }
  };
  const inputRef = useRef(null);
  const initialSentRef = useRef(false);
  // Bumped on every "New chat" so an in-flight request from the conversation
  // just cleared can never land its reply into the fresh, empty one.
  const sessionRef = useRef(0);
  const abortRef = useRef(null);

  const loadChats = useCallback(() => {
    if (!user) { setChats([]); setArchivedChats([]); return; }
    const list = (data) => (Array.isArray(data) ? data : []);
    api.get("/ai/chats").then(({ data }) => setChats(list(data))).catch(() => {});
    api.get("/ai/chats", { params: { archived: true } }).then(({ data }) => setArchivedChats(list(data))).catch(() => {});
  }, [user]);
  useEffect(loadChats, [loadChats]);

  // Never shows a number the endpoint didn't return: anything unexpected clears it.
  const loadUsage = useCallback(async () => {
    try {
      const { data } = await api.get("/ai/usage");
      setUsage(data && typeof data === "object" && !Array.isArray(data) ? data : null);
    } catch {
      setUsage(null);
    }
  }, []);
  useEffect(() => { loadUsage(); }, [loadUsage, user]);

  const updateChat = async (id, patch) => {
    try {
      await api.patch(`/ai/chats/${encodeURIComponent(id)}`, patch);
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't update that chat."));
    }
    loadChats();
  };

  const confirmDelete = async () => {
    const id = pendingDelete?.conversation_id;
    if (!id) return;
    setDeleting(true);
    try {
      await api.delete(`/ai/chats/${encodeURIComponent(id)}`);
      const without = (list) => list.filter((c) => c.conversation_id !== id);
      setChats(without);
      setArchivedChats(without);
      if (id === conversationId) handleNewChat();
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't delete that chat. Please try again."));
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };

  // Cmd/Ctrl+K opens chat search (signed-in users: guests have no saved chats).
  useEffect(() => {
    if (!user) return undefined;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [user]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setDrawerOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

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
        mode,
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
      loadChats(); // a new chat appears, an old one moves to the top
    } catch (err) {
      if (sessionRef.current !== mySession) return;
      const limit = err?.response?.status === 429 ? err.response.data?.reason : null;
      if (limit && limit in LIMIT_ACTIONS) {
        const text = typeof err.response.data?.detail === "string" ? err.response.data.detail : "You've reached today's limit.";
        setMsgs((prev) => [...prev, { role: "assistant", text, limit }]);
        return;
      }
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
      loadUsage();
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
    setDrawerOpen(false);
    inputRef.current?.focus();
  };

  const openChat = async (id) => {
    setDrawerOpen(false);
    if (id === conversationId) return;
    handleNewChat();
    const mySession = sessionRef.current;
    try {
      const { data } = await api.get(`/ai/history/${encodeURIComponent(id)}`);
      if (sessionRef.current !== mySession) return;
      setConversationId(id);
      setMsgs((Array.isArray(data) ? data : []).map((m) => (m.role === "user"
        ? { role: "user", text: m.content } : assistantMessageFrom({ reply: m.content }))));
    } catch (err) {
      if (sessionRef.current !== mySession) return;
      toast.error(getErrorMessage(err, "Couldn't open that chat."));
      loadChats();
    }
  };

  // Stop: drop the in-flight answer (it never lands) and offer to resend the question.
  const stop = () => {
    const question = [...msgs].reverse().find((m) => m.role === "user")?.text;
    sessionRef.current += 1;
    abortRef.current?.abort();
    setLoading(false);
    setMsgs((prev) => [...prev, { role: "assistant", text: STOPPED_TEXT, retryText: question }]);
  };

  const copyAnswer = async (m) => {
    const text = m.answer ? answerPlainText(m.answer, cleanAssistantText) : cleanAssistantText(m.text);
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy. Please select the text instead.");
    }
  };

  const handleKeyDown = (e) => {
    // Enter sends, Shift+Enter is a new line; never send mid-IME-composition.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const usageView = formatUsage(usage);
  return (
    <div className="flex flex-1 h-full min-h-0 bg-background" data-testid="instant-legal-help-panel">
      <ConfirmDialog
        open={!!pendingDelete} onOpenChange={(open) => { if (!open) setPendingDelete(null); }} busy={deleting}
        title="Delete chat?" description="This chat will be permanently deleted. This can't be undone."
        confirmLabel="Delete" onConfirm={confirmDelete}
      />
      {user && <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} usage={usage} />}
      {helpOpen && <SupportTicketModal open onOpenChange={setHelpOpen} />}
      <ChatPalette open={paletteOpen} onOpenChange={setPaletteOpen} chats={chats} onSelect={openChat} />
      <ChatSidebar
        fullScreen={fullScreen} user={user} chats={chats} archivedChats={archivedChats} onUpdateChat={updateChat} onDeleteChat={setPendingDelete} usage={usage}
        onOpenSettings={() => setSettingsOpen(true)} onGetHelp={() => setHelpOpen(true)} onLogout={() => auth?.logout?.()} activeId={conversationId} onSelect={openChat}
        onNewChat={handleNewChat} newChatDisabled={msgs.length === 0 && !loading}
        collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)}
        drawerOpen={drawerOpen} onCloseDrawer={() => setDrawerOpen(false)}
      />
    <div className="flex flex-col flex-1 min-w-0 min-h-0">
      <div className="border-b border-border bg-white shrink-0">
        <div className="w-full px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button" onClick={() => setDrawerOpen(true)} aria-label="Open chats"
              className="md:hidden inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="chat-sidebar-open"
            >
              <Menu className="w-5 h-5" />
            </button>
            <h1 className="font-display font-bold text-base leading-tight truncate">Instant Legal Help</h1>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {/* Under 640px the pill gives way to the buttons (the drawer's usage block still shows it). */}
            {usageView && (
              <span className="mr-1 hidden rounded-full border border-border bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground sm:inline" title={usageView.detail} data-testid="chat-usage-pill">
                {usageView.pill}{usageView.reset && <span> · resets {usageView.reset}</span>}
              </span>
            )}
            {/* Guests have no saved chats, so search would do nothing for them. */}
            {user && (
              <button
                type="button" onClick={() => setPaletteOpen(true)} aria-label="Search chats" title="Search chats (Ctrl+K)"
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid="chat-header-search"
              >
                <Search className="h-5 w-5" />
              </button>
            )}
            <button
              type="button" onClick={handleNewChat} disabled={msgs.length === 0 && !loading} aria-label="New chat" title="New chat"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="chat-header-new"
            >
              <SquarePen className="h-5 w-5" />
            </button>
          </div>
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
            <div className="py-8 sm:py-16 text-center" data-testid="instant-legal-help-empty">
              <h2 className="font-display font-bold text-2xl sm:text-3xl">How can I help today?</h2>
              <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-6">
                Tell me what's going on and I'll help you figure out the next step.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-8 text-left">
                {SUGGESTIONS.map((text, i) => (
                  <button
                    key={text} type="button" onClick={() => send(text)}
                    className="rounded-xl border border-border bg-white p-4 text-sm leading-6 hover:border-accent/50 hover:bg-accent/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    data-testid={`instant-legal-help-suggestion-${i}`}
                  >
                    {text}
                  </button>
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
            <div key={i} className="cb-msg flex gap-3 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300" data-testid={`instant-legal-help-msg-assistant-${i}`}>
              <div className="w-8 h-8 rounded-lg bg-accent text-white shrink-0 flex items-center justify-center" aria-hidden="true" data-testid="instant-legal-help-avatar">
                <Scale className="w-4 h-4" />
              </div>
              <div className="min-w-0 flex-1 pt-0.5">
                {m.limit ? (
                  <LimitCard reason={m.limit} text={m.text} />
                ) : m.grounding === "insufficient" ? (
                  // Not a failure: the approved documents just don't cover it.
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 flex gap-3" data-testid="instant-legal-help-insufficient">
                    <Info className="w-4 h-4 text-amber-700 shrink-0 mt-1" aria-hidden="true" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-amber-800 uppercase tracking-wide">Not covered by the available documents</div>
                      <div className="mt-1"><ChatMarkdown text={cleanAssistantText(m.text)} citeLinks={webCitationLinks(m.citations)} /></div>
                    </div>
                  </div>
                ) : m.answer ? (
                  <AnswerCard answer={m.answer} citeLinks={documentCitationLinks(m.citations, `${chatId}-msg-${i}`)} clean={cleanAssistantText} />
                ) : (
                  <div className="space-y-3">
                    <ChatMarkdown text={cleanAssistantText(m.text)} citeLinks={webCitationLinks(m.citations)} />
                    <AnswerNote note={m.note} detail={m.noteDetail} clean={cleanAssistantText} />
                  </div>
                )}
                <ChatSources citations={m.citations} idPrefix={`${chatId}-msg-${i}`} />
                {hasActions(m) && (
                  // Hover/focus reveal on pointer devices (index.css .cb-msg-actions); the latest answer keeps them shown.
                  <div className="cb-msg-actions mt-2 flex items-center gap-1" data-always={i === msgs.length - 1 ? "" : undefined} data-testid="instant-legal-help-msg-actions">
                    <button
                      type="button" onClick={() => copyAnswer(m)} aria-label="Copy answer" title="Copy"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      data-testid="instant-legal-help-copy"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                  </div>
                )}
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
        <div className="max-w-[760px] mx-auto w-full px-4 pt-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm focus-within:border-accent/60 focus-within:ring-2 focus-within:ring-accent/20 transition-shadow">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={loading ? "Generating answer..." : msgs.length ? "Ask a follow-up..." : "Describe your situation, legal issue, or service need..."}
              aria-label="Message Instant Legal Help"
              autoFocus
              className="block w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-6 max-h-40 overflow-y-auto cb-scroll placeholder:text-slate-400 focus:outline-none"
              data-testid="instant-legal-help-input"
            />
            <div className="flex items-center gap-2 pt-1">
              <button
                type="button" disabled title="Coming soon" aria-label="Attach a file (coming soon)"
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground disabled:opacity-50"
                data-testid="instant-legal-help-attach"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <div
                role="group" aria-label="Answer style"
                className="inline-flex rounded-lg border border-border bg-muted p-0.5"
                data-testid="instant-legal-help-mode"
              >
                {MODES.map((m) => (
                  <button
                    key={m.value} type="button" aria-pressed={mode === m.value} onClick={() => chooseMode(m.value)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      mode === m.value ? "bg-white text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                    data-testid={`instant-legal-help-mode-${m.value}`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              {loading ? (
                <Button
                  type="button" onClick={stop} aria-label="Stop generating" title="Stop generating"
                  className="ml-auto h-10 w-10 shrink-0 rounded-full bg-foreground p-0 hover:bg-foreground/90"
                  data-testid="instant-legal-help-stop"
                >
                  <Square className="w-3.5 h-3.5 fill-current" />
                </Button>
              ) : (
                <Button
                  type="button" onClick={() => send()} disabled={!input.trim()}
                  aria-label="Send message"
                  className="ml-auto h-10 w-10 shrink-0 rounded-full bg-accent p-0 hover:bg-accent/90"
                  data-testid="instant-legal-help-send"
                >
                  <ArrowUp className="w-5 h-5" />
                </Button>
              )}
            </div>
          </div>
          <p className="text-2xs text-muted-foreground text-center mt-2 px-2">
            General guidance only, not a substitute for advice from a lawyer on your specific case.
          </p>
        </div>
      </div>
    </div>
    </div>
  );
}
