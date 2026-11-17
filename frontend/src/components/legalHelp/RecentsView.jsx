import React, { useCallback, useEffect, useRef, useState } from "react";
import { Archive, ArchiveRestore, Search, SquarePen, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { ChatMenu } from "./ChatSidebar";

const PAGE = 30;
const rtf = typeof Intl !== "undefined" && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat("en", { numeric: "always" }) : null;

/* "2 minutes ago", "4 days ago", then "Nov 5" (with the year when it isn't this year). Exported for tests. */
export function relativeTime(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const s = Math.max(0, (now - d) / 1000);
  if (s < 60) return "just now";
  if (rtf && s < 3600) return rtf.format(-Math.floor(s / 60), "minute");
  if (rtf && s < 86400) return rtf.format(-Math.floor(s / 3600), "hour");
  if (rtf && s < 7 * 86400) return rtf.format(-Math.floor(s / 86400), "day");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
}

function RecentsRow({ chat, selecting, selected, onToggle, onOpen, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const save = () => {
    const title = draft.trim();
    setEditing(false);
    if (title && title !== chat.title) onUpdate(chat.conversation_id, { title });
  };
  return (
    <li className="flex items-center gap-3 border-b border-border px-1 py-1 last:border-0" data-testid="recents-row">
      {selecting && (
        <Checkbox checked={selected} onCheckedChange={() => onToggle(chat.conversation_id)}
          aria-label={`Select ${chat.title || "chat"}`} data-testid="recents-row-check" />
      )}
      {editing ? (
        <input
          autoFocus value={draft} maxLength={48} aria-label="Chat title"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); save(); }
            if (e.key === "Escape") { e.preventDefault(); setEditing(false); }
          }}
          onBlur={() => setEditing(false)}
          className="min-w-0 flex-1 rounded-lg border border-accent/60 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30"
          data-testid="recents-row-rename"
        />
      ) : (
        <button
          type="button" onClick={() => (selecting ? onToggle(chat.conversation_id) : onOpen(chat.conversation_id))}
          className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-lg px-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid="recents-row-open"
        >
          <span className="min-w-0 flex-1 truncate text-sm font-medium" title={chat.title}>{chat.title || "New chat"}</span>
          {chat.pinned && <span className="shrink-0 rounded-full bg-accent/10 px-2 py-0.5 text-2xs font-semibold text-accent" data-testid="recents-pinned">Pinned</span>}
          <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{relativeTime(chat.updated_at)}</span>
        </button>
      )}
      {!selecting && (
        <ChatMenu
          chat={chat} onUpdate={onUpdate} onDelete={onDelete}
          onRename={() => { setDraft(chat.title || ""); setEditing(true); }}
          triggerClassName="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span aria-hidden="true" className="text-lg leading-none">···</span>
        </ChatMenu>
      )}
    </li>
  );
}

/* Every chat, paged from GET /ai/chats as the list scrolls, with Active /
   Archived tabs and a select mode for bulk archive / delete
   (POST /ai/chats/bulk). Shown in the chat's main area at /legal-help/chats. */
export default function RecentsView({ onOpen, onNewChat, onSearch, onUpdate, onDelete, onBulkDone, refreshKey }) {
  const [tab, setTab] = useState("active");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const reqRef = useRef(0);
  const sentinelRef = useRef(null);

  const load = useCallback(async (offset) => {
    const req = offset ? reqRef.current : ++reqRef.current; // a fresh list supersedes pages still in flight
    setLoading(true);
    try {
      const { data } = await api.get("/ai/chats", { params: { archived: tab === "archived", limit: PAGE, offset } });
      if (req !== reqRef.current) return;
      const page = Array.isArray(data) ? data : [];
      setRows((prev) => (offset ? [...prev, ...page] : page));
      setHasMore(page.length === PAGE);
    } catch (err) {
      if (req !== reqRef.current) return;
      setHasMore(false);
      toast.error(getErrorMessage(err, "Couldn't load your chats."));
    } finally {
      if (req === reqRef.current) setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    setRows([]);
    setSelected(new Set());
    load(0);
  }, [load, refreshKey]);

  // Load the next page when the end of the list scrolls into view.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore || loading || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) load(rows.length); });
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, loading, rows.length, load]);

  const toggle = (id) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const stopSelecting = () => { setSelecting(false); setSelected(new Set()); };

  const bulk = async (action) => {
    const ids = [...selected];
    setBusy(true);
    try {
      const { data } = await api.post("/ai/chats/bulk", { action, ids });
      const n = data?.changed ?? 0;
      toast.success(`${n} chat${n === 1 ? "" : "s"} ${action === "delete" ? "deleted" : action === "archive" ? "archived" : "restored"}`);
      onBulkDone?.(action, ids);
      stopSelecting();
      load(0);
    } catch (err) {
      toast.error(getErrorMessage(err, "Couldn't update those chats. Please try again."));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  const pinned = rows.filter((c) => c.pinned);
  const ordered = [...pinned, ...rows.filter((c) => !c.pinned)];
  const iconButton = "inline-flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <div className="relative flex-1 min-h-0 overflow-y-auto cb-scroll" data-testid="chat-recents">
      <div className="mx-auto w-full max-w-3xl px-4 py-6">
        <h1 className="font-display text-2xl font-bold">Recents</h1>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
          <Tabs value={tab} onValueChange={(v) => { setTab(v); stopSelecting(); }}>
            <TabsList>
              <TabsTrigger value="active" data-testid="recents-tab-active">Active</TabsTrigger>
              <TabsTrigger value="archived" data-testid="recents-tab-archived">Archived</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-1">
            <button type="button" onClick={onSearch} aria-label="Search chats" className={iconButton} data-testid="recents-search">
              <Search className="h-5 w-5" />
            </button>
            <Button type="button" variant="outline" className="h-10" onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
              disabled={!rows.length && !selecting} data-testid="recents-select">
              {selecting ? <><X className="mr-1 h-4 w-4" />Cancel</> : "Select"}
            </Button>
            <Button type="button" className="h-10 bg-accent hover:bg-accent/90" onClick={onNewChat} data-testid="recents-new">
              <SquarePen className="mr-1.5 h-4 w-4" />New chat
            </Button>
          </div>
        </div>

        {loading && !rows.length ? (
          <ul className="mt-2 space-y-3" aria-label="Loading chats" data-testid="recents-loading">
            {[0, 1, 2, 3, 4].map((i) => <li key={i} className="h-10 rounded-lg bg-slate-200/70 motion-safe:animate-pulse" />)}
          </ul>
        ) : !rows.length ? (
          <p className="py-16 text-center text-sm text-muted-foreground" data-testid="recents-empty">
            {tab === "archived" ? "No archived chats." : "No chats yet. Start one with New chat."}
          </p>
        ) : (
          <ul className="mt-1" data-testid="recents-list">
            {ordered.map((c) => (
              <RecentsRow
                key={c.conversation_id} chat={c} selecting={selecting} selected={selected.has(c.conversation_id)}
                onToggle={toggle} onOpen={onOpen} onUpdate={onUpdate} onDelete={onDelete}
              />
            ))}
          </ul>
        )}
        {hasMore && <div ref={sentinelRef} className="h-10" data-testid="recents-more" />}
      </div>

      {selecting && (
        <div className="sticky bottom-0 border-t border-border bg-white/95 px-4 py-3 backdrop-blur" data-testid="recents-actions">
          <div className="mx-auto flex max-w-3xl items-center gap-2">
            <span className="flex-1 text-sm font-semibold" data-testid="recents-count">{selected.size} selected</span>
            <Button type="button" variant="outline" className="h-10" disabled={!selected.size || busy}
              onClick={() => bulk(tab === "archived" ? "unarchive" : "archive")} data-testid="recents-bulk-archive">
              {tab === "archived" ? <><ArchiveRestore className="mr-1.5 h-4 w-4" />Unarchive</> : <><Archive className="mr-1.5 h-4 w-4" />Archive</>}
            </Button>
            <Button type="button" variant="destructive" className="h-10" disabled={!selected.size || busy}
              onClick={() => setConfirming(true)} data-testid="recents-bulk-delete">
              <Trash2 className="mr-1.5 h-4 w-4" />Delete
            </Button>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={confirming} onOpenChange={setConfirming} busy={busy}
        title={`Delete ${selected.size} chat${selected.size === 1 ? "" : "s"}?`}
        description="These chats will be permanently deleted. This can't be undone."
        confirmLabel="Delete" onConfirm={() => bulk("delete")}
      />
    </div>
  );
}
