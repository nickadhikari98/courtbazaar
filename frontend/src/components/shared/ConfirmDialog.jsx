import React from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

/* Destructive-action confirm shell — this Dialog/Cancel/confirm-button chrome
   was hand-duplicated across every "delete/deactivate this?" dialog in the
   admin pages (AdminLeads' single + bulk delete, AdminUsers' deactivate)
   with identical structure, drifting only in copy. Business logic — what
   onConfirm does, whether/when it closes the dialog — stays with the caller;
   this only owns the chrome. */
export default function ConfirmDialog({
  open,
  onOpenChange,
  busy = false,
  title,
  description,
  confirmLabel = "Confirm",
  confirmIcon: ConfirmIcon,
  confirmVariant = "destructive",
  cancelLabel = "Cancel",
  onConfirm,
}) {
  return (
    <Dialog open={open} onOpenChange={(v) => !busy && onOpenChange(v)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={confirmVariant} className="font-bold" onClick={onConfirm} disabled={busy}>
            {ConfirmIcon && <ConfirmIcon className="w-4 h-4 mr-1.5" />} {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
