import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Search, Trash2 } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { initialsOf } from "@/components/proxyCounsel/CounselCard";

function DeactivateUserDialog({ targetUser, open, onOpenChange, onDeactivated }) {
  const [busy, setBusy] = useState(false);

  const confirmDeactivate = async () => {
    if (!targetUser) return;
    setBusy(true);
    try {
      await api.put(`/admin/users/${targetUser.user_id}/deactivate`);
      toast.success("User deactivated");
      onOpenChange(false);
      onDeactivated?.(targetUser.user_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not deactivate this user");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      busy={busy}
      title="Deactivate this user?"
      description={(
        <>
          Are you sure you want to deactivate{" "}
          <b className="text-foreground">{targetUser?.name || "this user"}</b>? They will immediately lose access
          to CourtBazaar. Historical records will be preserved.
        </>
      )}
      confirmLabel="Deactivate User"
      confirmIcon={Trash2}
      onConfirm={confirmDeactivate}
    />
  );
}

/* "Delete selected" is a real, permanent delete (POST
   /admin/users/bulk-delete) for active and deactivated users alike — unlike
   the per-row button, which only deactivates. The backend decides per id
   and reports what it skipped (self, admins, money still in escrow/wallet),
   so skipped users stay in the list and stay selected. */
function BulkDeleteUsersDialog({ users, open, onOpenChange, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const count = users.length;

  const confirmDelete = async () => {
    if (!count) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/users/bulk-delete", { user_ids: users.map((u) => u.user_id) });
      const deletedIds = data?.deleted || [];
      const skipped = data?.skipped || [];

      if (deletedIds.length) {
        toast.success(`${deletedIds.length} user${deletedIds.length === 1 ? "" : "s"} permanently deleted`);
        onDeleted?.(deletedIds);
      }
      if (skipped.length) {
        const reasons = [...new Set(skipped.map((s) => s.reason))].join("; ");
        toast.error(`${skipped.length} user${skipped.length === 1 ? "" : "s"} could not be deleted: ${reasons}`);
      }
      if (deletedIds.length > 0 || skipped.length === 0) onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete the selected users");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      busy={busy}
      title="ARE YOU SURE?"
      description="This will permanently delete the selected users and cannot be undone."
      confirmLabel={`Delete selected${count > 1 ? ` (${count})` : ""}`}
      confirmIcon={Trash2}
      onConfirm={confirmDelete}
    />
  );
}

export default function AdminUsers() {
  const { user: currentAdmin } = useAuth();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const load = () => api.get("/admin/users").then(r => setUsers(r.data));

  useEffect(() => { load(); }, []);

  const handleDeactivated = (userId) => {
    setUsers((prev) => prev.map((u) => (u.user_id === userId ? { ...u, deleted: true } : u)));
    setSelectedIds((prev) => { const next = new Set(prev); next.delete(userId); return next; });
  };

  const handleBulkDeleted = (userIds) => {
    const idSet = new Set(userIds);
    setUsers((prev) => prev.filter((u) => !idSet.has(u.user_id)));
    setSelectedIds((prev) => { const next = new Set(prev); userIds.forEach((id) => next.delete(id)); return next; });
    load().catch(() => toast.error("Could not refresh the user list"));
  };

  // The signed-in admin and other admins are never selectable. Deactivated
  // accounts can be selected, but only active ones get the per-row
  // deactivate button.
  const canSelect = (u) => u.role !== "admin" && u.user_id !== currentAdmin?.user_id;
  const canDeactivate = (u) => !u.deleted && canSelect(u);

  const filtered = users.filter(u =>
    !q || u.name?.toLowerCase().includes(q.toLowerCase()) || u.email?.toLowerCase().includes(q.toLowerCase())
  );

  // Selection is always read through the visible, selectable rows, so a user
  // hidden by the search box (or one that became protected after a refresh)
  // can never be part of a bulk delete.
  const selectable = filtered.filter(canSelect);
  const selectedUsers = selectable.filter((u) => selectedIds.has(u.user_id));
  const allVisibleSelected = selectable.length > 0 && selectedUsers.length === selectable.length;

  const toggleSelect = (userId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId); else next.add(userId);
      return next;
    });
  };
  const toggleSelectAll = () => {
    setSelectedIds(allVisibleSelected ? new Set() : new Set(selectable.map((u) => u.user_id)));
  };

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Users</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">All users ({users.length})</h1>

      <div className="relative mb-4">
        <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email…" className="pl-10" data-testid="admin-users-search" />
      </div>

      {selectable.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 px-1" data-testid="admin-users-bulk-toolbar">
          <label className="flex items-center gap-2 text-sm text-muted-foreground font-semibold cursor-pointer select-none">
            <Checkbox checked={allVisibleSelected} onCheckedChange={toggleSelectAll} data-testid="admin-users-select-all" />
            Select all
          </label>
          {selectedUsers.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold" data-testid="admin-users-selected-count">{selectedUsers.length} selected</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())} data-testid="admin-users-clear-selection">
                Clear
              </Button>
              <Button type="button" variant="destructive" size="sm" className="font-bold" onClick={() => setBulkDeleteOpen(true)} data-testid="admin-users-delete-selected">
                <Trash2 className="w-4 h-4 mr-1.5" /> Delete selected
              </Button>
            </div>
          )}
        </div>
      )}

      <Card className="dashboard-card border-none">
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {filtered.map(u => {
              const initials = initialsOf(u.name || "U");
              const selectableRow = canSelect(u);
              return (
                <div key={u.user_id} className="p-4 flex flex-wrap items-center gap-x-4 gap-y-2" data-testid={`admin-user-${u.user_id}`}>
                  {/* This group takes the full row on mobile (basis-full) so the
                      name/email column truncates against the whole row width
                      instead of whatever's left after the badges — at basis-auto
                      widths it was being squeezed down to a couple of characters,
                      and before truncate existed at all a long name/email simply
                      overflowed underneath the badges (see git history). */}
                  <div className="flex items-center gap-4 min-w-0 flex-1 basis-full sm:basis-auto">
                    {/* Protected (admin) rows keep a disabled box so the
                        avatars stay aligned with the selectable ones. */}
                    <Checkbox
                      checked={selectableRow && selectedIds.has(u.user_id)}
                      onCheckedChange={() => selectableRow && toggleSelect(u.user_id)}
                      disabled={!selectableRow}
                      aria-label={`Select ${u.name || "user"}`}
                      data-testid={`admin-user-select-${u.user_id}`}
                    />
                    <Avatar className="w-10 h-10 flex-shrink-0"><AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback></Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="font-display font-bold text-sm truncate">{u.name}</div>
                      <div className="text-xs text-muted-foreground truncate">{u.email} · {u.phone || "—"}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-auto sm:ml-0">
                    <Badge className="bg-secondary text-foreground border-0 font-bold capitalize text-2xs">{u.role?.replace('_', ' ')}</Badge>
                    <Badge variant="outline" className="font-bold capitalize text-2xs">{u.subscription}</Badge>
                    {u.deleted && (
                      <Badge className="bg-red-100 text-red-700 border-0 font-bold uppercase text-2xs">Deactivated</Badge>
                    )}
                    {canDeactivate(u) && (
                      <button
                        type="button"
                        title="Deactivate user"
                        aria-label="Deactivate user"
                        onClick={() => setDeactivateTarget(u)}
                        className="p-1.5 rounded-md text-red-600 hover:bg-red-50 flex-shrink-0"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <DeactivateUserDialog
        targetUser={deactivateTarget}
        open={!!deactivateTarget}
        onOpenChange={(v) => !v && setDeactivateTarget(null)}
        onDeactivated={handleDeactivated}
      />

      <BulkDeleteUsersDialog
        users={selectedUsers}
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        onDeleted={handleBulkDeleted}
      />
    </PageContainer>
  );
}
