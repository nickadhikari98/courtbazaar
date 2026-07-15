import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { ShieldCheck, Star, MapPin } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

export default function AdminVendors() {
  const [vendors, setVendors] = useState([]);
  const [status, setStatus] = useState("pending");

  const load = (s) => api.get("/admin/vendors", { params: { status: s } }).then(r => setVendors(r.data));
  useEffect(() => { load(status); }, [status]);

  const approve = async (id) => {
    try {
      await api.put(`/vendors/${id}/approve`);
      toast.success("Vendor approved");
      load(status);
    } catch { toast.error("Could not approve"); }
  };

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Vendors</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Vendor management</h1>

      <Tabs value={status} onValueChange={setStatus}>
        <TabsList data-testid="vendor-status-tabs">
          <TabsTrigger value="pending" data-testid="tab-vendors-pending">Pending KYC</TabsTrigger>
          <TabsTrigger value="approved" data-testid="tab-vendors-approved">Approved</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="mt-5 space-y-3">
        {vendors.length === 0 && <div className="text-center text-muted-foreground py-10">No vendors</div>}
        {vendors.map(v => (
          <Card key={v.vendor_id} className="dashboard-card border-none" data-testid={`admin-vendor-${v.vendor_id}`}>
            <CardContent className="p-5 flex flex-wrap items-start gap-4 justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="font-display font-bold text-lg">{v.shop_name}</div>
                  {v.kyc_status === 'approved' && <ShieldCheck className="w-4 h-4 text-emerald-600" />}
                </div>
                <div className="text-sm text-muted-foreground flex items-center gap-1.5 font-semibold"><MapPin className="w-3.5 h-3.5" /> {v.address}</div>
                <div className="text-xs text-muted-foreground mt-1">Owner: {v.owner_name} · {v.phone} · GST: {v.gst || "—"}</div>
                <div className="mt-2 flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1 font-bold"><Star className="w-3 h-3 text-accent fill-accent" /> {v.rating?.toFixed(1) || "—"}</span>
                  <span className="font-semibold">{v.court_ids?.length} courts</span>
                  <span className="font-semibold">{v.service_ids?.length} services</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={`${v.kyc_status === 'approved' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'} border-0 font-bold uppercase`}>{v.kyc_status}</Badge>
                {v.kyc_status !== "approved" && (
                  <Button onClick={() => approve(v.vendor_id)} className="bg-accent font-bold" data-testid={`approve-vendor-${v.vendor_id}`}>Approve</Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </PageContainer>
  );
}
