import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Search } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => { api.get("/admin/users").then(r => setUsers(r.data)); }, []);

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
              const initials = (u.name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase();
              return (
                <div key={u.user_id} className="p-4 flex items-center gap-4" data-testid={`admin-user-${u.user_id}`}>
                  <Avatar className="w-10 h-10"><AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback></Avatar>
                  <div className="min-w-0 flex-1">
                    <div className="font-display font-bold text-sm">{u.name}</div>
                    <div className="text-xs text-muted-foreground">{u.email} · {u.phone || "—"}</div>
                  </div>
                  <Badge className="bg-secondary text-foreground border-0 font-bold capitalize text-2xs">{u.role?.replace('_', ' ')}</Badge>
                  <Badge variant="outline" className="font-bold capitalize text-2xs">{u.subscription}</Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
