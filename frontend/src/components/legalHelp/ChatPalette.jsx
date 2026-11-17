import React, { useRef } from "react";
import { ArrowLeft, MessageSquare, Pin } from "lucide-react";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

/* Chat search, from Cmd/Ctrl+K, the header's search button or "View all".
   Radix Dialog gives the focus trap, role="dialog", Esc and the dimmed
   overlay; cmdk gives arrow keys, Enter and the filtering. No search
   endpoint: titles only. A centred dialog from 768px up; below that a
   full-screen sheet with a back arrow and full-width rows. */
export default function ChatPalette({ open, onOpenChange, chats, onSelect }) {
  const inputRef = useRef(null);
  const pinned = chats.filter((c) => c.pinned);
  const recent = chats.filter((c) => !c.pinned);
  const item = (c, Icon) => (
    <CommandItem
      key={c.conversation_id}
      // The id keeps two chats with the same title apart.
      value={`${c.title || "New chat"} ${c.conversation_id}`}
      onSelect={() => { onOpenChange(false); onSelect(c.conversation_id); }}
      className="max-md:min-h-12"
      data-testid="chat-palette-item"
    >
      <Icon className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="truncate">{c.title || "New chat"}</span>
    </CommandItem>
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={"overflow-hidden p-0 max-w-[calc(100vw-2rem)] sm:max-w-lg "
          + "max-md:inset-0 max-md:left-0 max-md:top-0 max-md:flex max-md:h-[100dvh] max-md:max-w-none max-md:translate-x-0 "
          + "max-md:translate-y-0 max-md:flex-col max-md:rounded-none max-md:border-0 max-md:[&>button:last-child]:hidden"}
        // The search field, not the back arrow, gets focus, so the phone keyboard comes up.
        onOpenAutoFocus={(e) => { e.preventDefault(); inputRef.current?.focus(); }}
        aria-describedby={undefined}
        data-testid="chat-palette"
      >
        <DialogTitle className="sr-only">Search chats</DialogTitle>
        <Command className="max-md:flex-1 max-md:min-h-0 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground">
          <div className="relative flex items-center">
            <DialogClose
              aria-label="Back"
              className="ml-1 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="chat-palette-back"
            >
              <ArrowLeft className="h-5 w-5" />
            </DialogClose>
            <div className="min-w-0 flex-1">
              <CommandInput ref={inputRef} placeholder="Search chats and saved answers" className="h-12 md:pr-14" data-testid="chat-palette-input" />
            </div>
            <kbd className="pointer-events-none absolute right-12 top-1/2 hidden -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-2xs font-semibold text-muted-foreground md:inline">Esc</kbd>
          </div>
          <CommandList className="max-h-80 max-md:max-h-none max-md:flex-1">
            <CommandEmpty>No chats found.</CommandEmpty>
            {pinned.length > 0 && <CommandGroup heading="Pinned">{pinned.map((c) => item(c, Pin))}</CommandGroup>}
            {recent.length > 0 && <CommandGroup heading="Recent">{recent.map((c) => item(c, MessageSquare))}</CommandGroup>}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
