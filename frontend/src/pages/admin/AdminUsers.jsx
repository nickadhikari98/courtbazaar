import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
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

export default function AdminUsers() {
  const { user: currentAdmin } = useAuth();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const load = () => { api.get("/admin/users").then(r => setUsers(r.data)); };

  useEffect(() => { load(); }, []);

  const handleDeactivated = (userId) => {
    setUsers((prev) => prev.map((u) => (u.user_id === userId ? { ...u, deleted: true } : u)));
  };

  const filtered = users.filter(u =>
    !q || u.name?.toLowerCase().includes(q.toLowerCase()) || u.email?.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Users</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">All users ({users.length})</h1>

      <div className="relative mb-4">
        <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email…" className="pl-10" data-testid="admin-users-search" />
      </div>

      <Card className="dashboard-card border-none">
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {filtered.map(u => {
              const initials = initialsOf(u.name || "U");
              const canDeactivate = !u.deleted && u.role !== "admin" && u.user_id !== currentAdmin?.user_id;
              return (
                <div key={u.user_id} className="p-4 flex items-center gap-4" data-testid={`admin-user-${u.user_id}`}>
                  <Avatar className="w-10 h-10"><AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback></Avatar>
                  <div className="min-w-0 flex-1">
                    <div className="font-display font-bold text-sm">{u.name}</div>
                    <div className="text-xs text-muted-foreground">{u.email} · {u.phone || "—"}</div>
                  </div>
                  <Badge className="bg-secondary text-foreground border-0 font-bold capitalize text-2xs">{u.role?.replace('_', ' ')}</Badge>
                  <Badge variant="outline" className="font-bold capitalize text-2xs">{u.subscription}</Badge>
                  {u.deleted && (
                    <Badge className="bg-red-100 text-red-700 border-0 font-bold uppercase text-2xs">Deactivated</Badge>
                  )}
                  {canDeactivate && (
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
    </PageContainer>
  );
}
