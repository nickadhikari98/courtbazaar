import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Package, Search, ArrowRight } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => { api.get("/orders").then(r => { setOrders(r.data || []); setLoading(false); }); }, []);

  const filter = (list) => list.filter(o =>
    !q || o.order_id.toLowerCase().includes(q.toLowerCase()) ||
    (o.court_name || '').toLowerCase().includes(q.toLowerCase())
  );

  const tabs = {
    all: orders,
    active: orders.filter(o => !["completed", "delivered", "cancelled"].includes(o.status)),
    completed: orders.filter(o => ["completed", "delivered"].includes(o.status)),
    cancelled: orders.filter(o => o.status === "cancelled"),
  };

  const OrderCard = ({ o }) => (
    <Link to={`/orders/${o.order_id}`} data-testid={`order-row-${o.order_id}`}>
      <Card className="dashboard-card hover:shadow-md transition-all border-none">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="font-mono text-xs font-bold text-muted-foreground">{o.order_id}</span>
                <Badge className="bg-accent/10 text-accent border-0 text-2xs uppercase font-bold">{o.status.replace(/_/g, ' ')}</Badge>
                <Badge variant="outline" className={`text-2xs font-bold ${o.payment_status === 'paid' ? 'border-emerald-300 text-emerald-700' : ''}`}>
                  {o.payment_status === 'paid' ? 'PAID' : 'UNPAID'}
                </Badge>
              </div>
              <div className="font-display font-bold text-lg truncate">{o.court_name || o.court_id}</div>
              <div className="text-sm text-muted-foreground font-medium">{o.services?.length || 0} services · {o.delivery_option} · {new Date(o.created_at).toLocaleDateString('en-IN')}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-display font-black text-lg">{formatINR(o.pricing?.total)}</div>
              <ArrowRight className="w-4 h-4 ml-auto mt-1 text-muted-foreground" />
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Order history</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1 mb-6">My Orders</h1>

      <div className="relative mb-6">
        <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by order ID or court…" className="pl-10" data-testid="orders-search-input" />
      </div>

      <Tabs defaultValue="active">
        <TabsList data-testid="orders-tabs">
          <TabsTrigger value="active" data-testid="tab-active">Active ({tabs.active.length})</TabsTrigger>
          <TabsTrigger value="completed" data-testid="tab-completed">Completed ({tabs.completed.length})</TabsTrigger>
          <TabsTrigger value="all" data-testid="tab-all">All ({tabs.all.length})</TabsTrigger>
        </TabsList>
        {Object.entries(tabs).map(([k, list]) => (
          <TabsContent value={k} key={k} className="mt-4 space-y-3">
            {loading ? [1,2,3].map(i => <div key={i} className="h-24 shimmer rounded-xl"></div>) :
              filter(list).length === 0 ? (
                <Card className="border-dashed border-2">
                  <CardContent className="p-10 text-center">
                    <Package className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                    <div className="font-display font-bold">No orders yet</div>
                    <p className="text-sm text-muted-foreground mt-1">Place your first order — it takes 30 seconds.</p>
                  </CardContent>
                </Card>
              ) : filter(list).map(o => <OrderCard key={o.order_id} o={o} />)}
          </TabsContent>
        ))}
      </Tabs>
    </PageContainer>
  );
}
