import React from "react";
import { MessageSquare, Pin } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

/* Cmd/Ctrl+K: search the chats already loaded in the sidebar. Radix Dialog
   gives the focus trap, role="dialog", Esc and the dimmed overlay; cmdk gives
   arrow keys, Enter and the filtering. No search endpoint: titles only. */
export default function ChatPalette({ open, onOpenChange, chats, onSelect }) {
  const pinned = chats.filter((c) => c.pinned);
  const recent = chats.filter((c) => !c.pinned);
  const item = (c, Icon) => (
    <CommandItem
      key={c.conversation_id}
      // The id keeps two chats with the same title apart.
      value={`${c.title || "New chat"} ${c.conversation_id}`}
      onSelect={() => { onOpenChange(false); onSelect(c.conversation_id); }}
      data-testid="chat-palette-item"
    >
      <Icon className="mr-2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <span className="truncate">{c.title || "New chat"}</span>
    </CommandItem>
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-lg overflow-hidden p-0" aria-describedby={undefined} data-testid="chat-palette">
        <DialogTitle className="sr-only">Search chats</DialogTitle>
        <Command className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground">
          <div className="relative">
            <CommandInput placeholder="Search chats and saved answers" className="h-12 pr-14" data-testid="chat-palette-input" />
            <kbd className="pointer-events-none absolute right-12 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-2xs font-semibold text-muted-foreground">Esc</kbd>
          </div>
          <CommandList className="max-h-80">
            <CommandEmpty>No chats found.</CommandEmpty>
            {pinned.length > 0 && <CommandGroup heading="Pinned">{pinned.map((c) => item(c, Pin))}</CommandGroup>}
            {recent.length > 0 && <CommandGroup heading="Recent">{recent.map((c) => item(c, MessageSquare))}</CommandGroup>}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
