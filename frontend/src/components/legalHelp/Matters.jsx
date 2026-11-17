import React, { useCallback, useEffect, useState } from "react";
import { FolderOpen, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { RecentsRow } from "./RecentsView";

/* Matters: folders that group chats and carry custom instructions
   (backend chat_matters). No uploads yet. */
export const MATTER_INSTRUCTIONS_MAX = 2000;

/* A one-field name dialog: "New matter", "Rename matter". */
export function NameDialog({ open, onOpenChange, title, label = "Name", initial = "", confirmLabel = "Save", onSubmit }) {
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setName(initial); }, [open, initial]);
  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try { await onSubmit(name.trim()); onOpenChange(false); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined} data-testid="name-dialog">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle></DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="name-dialog-input">{label}</Label>
            <Input id="name-dialog-input" autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} data-testid="name-dialog-input" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button type="submit" disabled={busy || !name.trim()} data-testid="name-dialog-save">{confirmLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* "Move to matter": the user's matters, "New matter...", and "Remove from
   matter" when the chat is in one. */
export function MoveToMatterDialog({ chat, matters, onOpenChange, onMove, onCreate }) {
  const [naming, setNaming] = useState(false);
  const open = !!chat;
  return (
    <>
      <Dialog open={open && !naming} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-sm" aria-describedby={undefined} data-testid="move-dialog">
          <DialogHeader><DialogTitle className="font-display">Move to matter</DialogTitle></DialogHeader>
          <ul className="max-h-72 space-y-1 overflow-y-auto cb-scroll">
            {matters.map((m) => (
              <li key={m.matter_id}>
                <button
                  type="button" onClick={() => onMove(chat, m.matter_id)} disabled={chat?.matter_id === m.matter_id}
                  className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm hover:bg-secondary disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  data-testid="move-dialog-matter"
                >
                  <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" /><span className="truncate">{m.name}</span>
                </button>
              </li>
            ))}
            <li>
              <button type="button" onClick={() => setNaming(true)}
                className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm font-semibold text-accent hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid="move-dialog-new">
                New matter...
              </button>
            </li>
            {chat?.matter_id && (
              <li>
                <button type="button" onClick={() => onMove(chat, null)}
                  className="flex min-h-11 w-full items-center rounded-lg px-3 text-left text-sm text-muted-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  data-testid="move-dialog-remove">
                  Remove from matter
                </button>
              </li>
            )}
          </ul>
        </DialogContent>
      </Dialog>
      <NameDialog
        open={open && naming} onOpenChange={(o) => { if (!o) setNaming(false); }} title="New matter" confirmLabel="Create and move"
        onSubmit={async (name) => { const m = await onCreate(name); if (m) await onMove(chat, m.matter_id); setNaming(false); }}
      />
    </>
  );
}

/* One matter in the main area: name (rename in place), custom instructions,
   and its chats with the usual row menu. */
export function MatterView({ matter, refreshKey, onOpen, onUpdate, onDelete, onMove, onRenameMatter, onSaveInstructions, onDeleteMatter }) {
  const [chats, setChats] = useState(null);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState(false);
  const matterId = matter?.matter_id;

  const load = useCallback(async () => {
    if (!matterId) return;
    try {
      const { data } = await api.get("/ai/chats", { params: { matter_id: matterId, limit: 100 } });
      setChats(Array.isArray(data) ? data : []);
    } catch (err) {
      setChats([]);
      toast.error(getErrorMessage(err, "Couldn't load this matter's chats."));
    }
  }, [matterId]);
  useEffect(() => { setChats(null); load(); }, [load, refreshKey]);

  if (!matter) {
    return <div className="flex-1 p-8 text-center text-sm text-muted-foreground" data-testid="matter-missing">This matter isn't available.</div>;
  }
  const saveName = () => {
    const name = nameDraft.trim();
    setRenaming(false);
    if (name && name !== matter.name) onRenameMatter(matter, name);
  };
  return (
    <div className="flex-1 min-h-0 overflow-y-auto cb-scroll" data-testid="matter-view">
      <div className="mx-auto w-full max-w-3xl px-4 py-6">
        <div className="flex items-center gap-2">
          <FolderOpen className="h-6 w-6 shrink-0 text-accent" aria-hidden="true" />
          {renaming ? (
            <input
              autoFocus value={nameDraft} maxLength={80} aria-label="Matter name"
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); saveName(); }
                if (e.key === "Escape") { e.preventDefault(); setRenaming(false); }
              }}
              onBlur={() => setRenaming(false)}
              className="min-w-0 flex-1 rounded-lg border border-accent/60 bg-card px-2 py-1 font-display text-xl font-bold focus:outline-none focus:ring-2 focus:ring-accent/30"
              data-testid="matter-rename"
            />
          ) : (
            <h1 className="min-w-0 flex-1 truncate font-display text-2xl font-bold" title={matter.name} data-testid="matter-name">{matter.name}</h1>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger aria-label="Matter options" data-testid="matter-menu"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <MoreHorizontal className="h-5 w-5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem onSelect={() => setTimeout(() => { setNameDraft(matter.name); setRenaming(true); }, 0)} data-testid="matter-rename-item">
                <Pencil className="mr-2 h-4 w-4" />Rename
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setTimeout(() => setConfirming(true), 0)}
                className="text-destructive focus:bg-destructive/10 focus:text-destructive" data-testid="matter-delete-item">
                <Trash2 className="mr-2 h-4 w-4" />Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <section className="mt-5 rounded-xl border border-border bg-card p-4" data-testid="matter-instructions">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Custom instructions</h2>
            {!editing && (
              <Button type="button" variant="outline" size="sm" className="h-9" onClick={() => { setDraft(matter.custom_instructions || ""); setEditing(true); }}
                data-testid="matter-instructions-edit">Edit</Button>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">Applies to all chats in this matter</p>
          {editing ? (
            <div className="mt-3 space-y-2">
              <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={MATTER_INSTRUCTIONS_MAX} rows={5}
                aria-label="Custom instructions" placeholder="For example: keep answers short; I'm a junior advocate preparing for a DIAC hearing."
                data-testid="matter-instructions-input" />
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground tabular-nums">{draft.length} / {MATTER_INSTRUCTIONS_MAX}</span>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
                  <Button type="button" size="sm" data-testid="matter-instructions-save"
                    onClick={async () => { await onSaveInstructions(matter, draft.trim()); setEditing(false); }}>Save</Button>
                </div>
              </div>
            </div>
          ) : (
            <p className={`mt-3 whitespace-pre-wrap text-sm ${matter.custom_instructions ? "" : "text-muted-foreground"}`} data-testid="matter-instructions-text">
              {matter.custom_instructions || "No instructions yet."}
            </p>
          )}
        </section>

        <h2 className="mt-6 text-sm font-semibold">Chats</h2>
        {chats === null ? (
          <ul className="mt-2 space-y-3" aria-label="Loading chats">
            {[0, 1, 2].map((i) => <li key={i} className="h-10 rounded-lg bg-border motion-safe:animate-pulse" />)}
          </ul>
        ) : chats.length ? (
          <ul className="mt-1" data-testid="matter-chats">
            {chats.map((c) => (
              <RecentsRow key={c.conversation_id} chat={c} onOpen={onOpen} onUpdate={onUpdate} onDelete={onDelete} onMove={onMove} />
            ))}
          </ul>
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="matter-empty">
            No chats in this matter yet. Use "Move to matter" on any chat to add it.
          </p>
        )}
      </div>
      <ConfirmDialog
        open={confirming} onOpenChange={setConfirming}
        title="Delete matter?" description="The matter and its custom instructions will be deleted. Its chats are kept and go back to your chat list."
        confirmLabel="Delete matter" onConfirm={async () => { setConfirming(false); await onDeleteMatter(matter); }}
      />
    </div>
  );
}
