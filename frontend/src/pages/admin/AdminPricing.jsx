import React, { useEffect, useState } from "react";
import { api, formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Edit3, Save } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";

const VISIBILITY_SURFACES = [
  { key: "landing", label: "Landing" },
  { key: "marketplace", label: "Marketplace" },
  { key: "sidebar", label: "Sidebar" },
];

export default function AdminPricing() {
  const [services, setServices] = useState([]);
  const [edit, setEdit] = useState({});

  // include_hidden: this screen is where a founder flips a service's
  // per-surface visibility, so it must show services that are currently
  // hidden from Marketplace too — not just what /services returns by default.
  const load = () => api.get("/services", { params: { include_hidden: true } }).then(r => setServices(r.data));
  useEffect(() => { load(); }, []);

  const startEdit = (s) => setEdit({
    ...edit,
    [s.service_id]: {
      base_price: s.base_price,
      platform_commission_pct: s.platform_commission_pct || 0.2,
      active: s.active !== false,
      visibility: { landing: false, marketplace: false, sidebar: false, ...(s.visibility || {}) },
    },
  });

  const save = async (id) => {
    const e = edit[id];
    try {
      await api.put(`/admin/services/${id}/pricing`, {
        service_id: id,
        base_price: parseFloat(e.base_price),
        platform_commission_pct: e.platform_commission_pct !== undefined ? parseFloat(e.platform_commission_pct) : undefined,
        active: e.active,
        visibility: e.visibility,
      });
      toast.success("Pricing & visibility updated");
      setEdit(s => { const c = {...s}; delete c[id]; return c; });
      load();
    } catch { toast.error("Update failed"); }
  };

  return (
    <PageContainer className="max-w-5xl">
      <div className="cb-overline text-accent">Admin · Pricing</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Service pricing controls</h1>

      <Card className="dashboard-card border-none">
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {services.map(s => {
              const isEdit = edit[s.service_id];
              return (
                <div key={s.service_id} className="p-5 flex flex-wrap items-center gap-4" data-testid={`pricing-row-${s.service_id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-bold">{s.name}</div>
                    <div className="text-xs cb-overline">{s.category}</div>
                  </div>
                  {!isEdit ? (
                    <>
                      <div className="text-right">
                        <div className="font-display font-bold">{formatINR(s.base_price)}</div>
                        <div className="text-xs text-muted-foreground font-semibold">{s.unit}</div>
                      </div>
                      <div className="text-right text-sm">
                        <div className="cb-overline">Commission</div>
                        <div className="font-bold">{((s.platform_commission_pct || 0.2) * 100).toFixed(0)}%</div>
                      </div>
                      <div className="flex flex-wrap gap-1 max-w-[9rem]">
                        {s.active === false && <Badge variant="outline" className="text-2xs uppercase text-muted-foreground">Inactive</Badge>}
                        {VISIBILITY_SURFACES.filter(({ key }) => s.visibility?.[key]).map(({ key, label }) => (
                          <Badge key={key} variant="outline" className="text-2xs uppercase">{label}</Badge>
                        ))}
                      </div>
                      <Button onClick={() => startEdit(s)} variant="outline" size="sm" data-testid={`edit-${s.service_id}`}>
                        <Edit3 className="w-3.5 h-3.5 mr-1" /> Edit
                      </Button>
                    </>
                  ) : (
                    <>
                      <div>
                        <div className="cb-overline mb-0.5">Price (₹)</div>
                        <Input className="w-24 h-9" type="number" value={isEdit.base_price} onChange={(e) => setEdit({...edit, [s.service_id]: {...isEdit, base_price: e.target.value}})} data-testid={`edit-price-${s.service_id}`} />
                      </div>
                      <div>
                        <div className="cb-overline mb-0.5">Commission %</div>
                        <Input className="w-24 h-9" type="number" step="0.01" value={isEdit.platform_commission_pct} onChange={(e) => setEdit({...edit, [s.service_id]: {...isEdit, platform_commission_pct: e.target.value}})} data-testid={`edit-comm-${s.service_id}`} />
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Checkbox id={`active-${s.service_id}`} checked={isEdit.active}
                                  onCheckedChange={(v) => setEdit({...edit, [s.service_id]: {...isEdit, active: !!v}})}
                                  data-testid={`edit-active-${s.service_id}`} />
                        <label htmlFor={`active-${s.service_id}`} className="text-xs font-semibold">Active</label>
                      </div>
                      <div className="flex flex-col gap-1">
                        <div className="cb-overline">Visible on</div>
                        <div className="flex items-center gap-3">
                          {VISIBILITY_SURFACES.map(({ key, label }) => (
                            <div key={key} className="flex items-center gap-1.5">
                              <Checkbox id={`vis-${key}-${s.service_id}`} checked={!!isEdit.visibility[key]}
                                        onCheckedChange={(v) => setEdit({...edit, [s.service_id]: {...isEdit, visibility: {...isEdit.visibility, [key]: !!v}}})}
                                        data-testid={`edit-visibility-${key}-${s.service_id}`} />
                              <label htmlFor={`vis-${key}-${s.service_id}`} className="text-xs font-semibold">{label}</label>
                            </div>
                          ))}
                        </div>
                      </div>
                      <Button onClick={() => save(s.service_id)} className="bg-accent font-bold" size="sm" data-testid={`save-${s.service_id}`}>
                        <Save className="w-3.5 h-3.5 mr-1" /> Save
                      </Button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
