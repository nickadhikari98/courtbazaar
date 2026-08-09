import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Search, Star, CheckCircle2, XCircle, Trash2, Pin, PinOff, ArrowUp, ArrowDown, Save,
} from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import {
  adminListReviews, adminGetReview, adminUpdateReview, adminChangeReviewStatus,
  adminDeleteReview, adminBulkReviewAction, adminReorderReviews, adminGetReviewStats,
} from "@/lib/reviewsApi";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

const STATUS_BADGE = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
};

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <div className="text-2xl font-display font-black tracking-tight">{value}</div>
      <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}

function ReviewDetailDialog({ reviewId, open, onOpenChange, onChanged }) {
  const [review, setReview] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !reviewId) return;
    adminGetReview(reviewId)
      .then((r) => { setReview(r); setForm(r); })
      .catch(() => toast.error("Could not load review"));
  }, [open, reviewId]);

  const changeStatus = async (status) => {
    setBusy(true);
    try {
      await adminChangeReviewStatus(reviewId, status);
      toast.success(`Review ${status}`);
      onChanged?.();
      onOpenChange(false);
    } catch {
      toast.error("Could not update status");
    } finally {
      setBusy(false);
    }
  };

  const saveEdits = async () => {
    setBusy(true);
    try {
      await adminUpdateReview(reviewId, {
        name: form.name, designation: form.designation, organization: form.organization,
        rating: Number(form.rating), review: form.review,
      });
      toast.success("Review updated");
      onChanged?.();
    } catch {
      toast.error("Could not save changes");
    } finally {
      setBusy(false);
    }
  };

  const toggleFeatured = async () => {
    setBusy(true);
    try {
      await adminUpdateReview(reviewId, { featured: !review.featured });
      const fresh = await adminGetReview(reviewId);
      setReview(fresh);
      setForm(fresh);
      onChanged?.();
    } catch {
      toast.error("Could not update");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await adminDeleteReview(reviewId);
      toast.success("Review deleted");
      onChanged?.();
      onOpenChange(false);
    } catch {
      toast.error("Could not delete review");
    } finally {
      setBusy(false);
    }
  };

  if (!review || !form) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>Loading…</DialogTitle></DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto cb-scroll">
        <DialogHeader>
          <DialogTitle className="font-display text-xl flex items-center gap-2">
            {review.name}
            <Badge className={`${STATUS_BADGE[review.status]} border-0 font-bold uppercase text-2xs`}>
              {review.status}
            </Badge>
            {review.featured && <Badge variant="outline" className="text-2xs font-bold uppercase">Featured</Badge>}
          </DialogTitle>
          <DialogDescription>
            Submitted {new Date(review.submitted_at).toLocaleString()}
          </DialogDescription>
        </DialogHeader>

        {review.photo_url && (
          <img src={review.photo_url} alt="" className="w-20 h-20 rounded-full object-cover border" />
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Name</label>
            <Input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Designation</label>
              <Input value={form.designation || ""} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Organization / Court</label>
              <Input value={form.organization || ""} onChange={(e) => setForm({ ...form, organization: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Rating</label>
            <div className="flex gap-1 mt-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" onClick={() => setForm({ ...form, rating: n })}>
                  <Star className={`w-5 h-5 ${n <= form.rating ? "fill-accent text-accent" : "text-slate-300"}`} />
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Review</label>
            <Textarea rows={4} value={form.review || ""} onChange={(e) => setForm({ ...form, review: e.target.value })} />
          </div>
          <Button type="button" variant="outline" onClick={saveEdits} disabled={busy} className="font-bold">
            <Save className="w-4 h-4 mr-1.5" /> Save changes
          </Button>
        </div>

        <div className="border-t pt-3 flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => changeStatus("approved")} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
            <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve
          </Button>
          <Button type="button" disabled={busy} onClick={() => changeStatus("rejected")} variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50">
            <XCircle className="w-4 h-4 mr-1.5" /> Reject
          </Button>
          <Button type="button" disabled={busy} onClick={toggleFeatured} variant="outline" className="font-bold">
            {review.featured ? <PinOff className="w-4 h-4 mr-1.5" /> : <Pin className="w-4 h-4 mr-1.5" />}
            {review.featured ? "Unfeature" : "Feature"}
          </Button>
          <Button type="button" disabled={busy} onClick={remove} variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50 ml-auto">
            <Trash2 className="w-4 h-4 mr-1.5" /> Delete
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminReviews() {
  const [reviews, setReviews] = useState([]);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [stats, setStats] = useState(null);
  const [activeReviewId, setActiveReviewId] = useState(null);
  const [selected, setSelected] = useState([]);

  const load = () => {
    adminListReviews({ status: status || undefined, q: q || undefined }).then(setReviews);
  };
  const loadStats = () => adminGetReviewStats().then(setStats).catch(() => {});

  useEffect(() => { load(); setSelected([]); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const refreshAll = () => { load(); loadStats(); };

  const toggleSelected = (reviewId) => {
    setSelected((prev) => prev.includes(reviewId) ? prev.filter((id) => id !== reviewId) : [...prev, reviewId]);
  };

  const runBulk = async (action) => {
    if (!selected.length) return;
    try {
      await adminBulkReviewAction(selected, action);
      toast.success(`${selected.length} review(s) updated`);
      setSelected([]);
      refreshAll();
    } catch {
      toast.error("Bulk action failed");
    }
  };

  const move = async (index, direction) => {
    const ids = reviews.map((r) => r.review_id);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    try {
      await adminReorderReviews(ids);
      load();
    } catch {
      toast.error("Could not reorder");
    }
  };

  const totalCount = useMemo(() => stats?.by_status
    ? Object.values(stats.by_status).reduce((a, v) => a + v, 0)
    : 0, [stats]);

  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Admin · Reviews</div>
      <h1 className="font-display font-black text-3xl tracking-tighter mt-1 mb-6">Review management</h1>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard label="Total Reviews" value={totalCount} />
          <StatCard label="Pending" value={stats.by_status.pending} />
          <StatCard label="Approved" value={stats.by_status.approved} />
          <StatCard label="Featured" value={stats.featured_count} />
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <Tabs value={status} onValueChange={setStatus} className="flex-1">
          <TabsList className="flex-wrap h-auto">
            {STATUS_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, organization, text" className="pl-8" />
        </div>
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-4 bg-accent/5 border border-accent/30 rounded-lg px-4 py-2.5">
          <span className="text-sm font-semibold">{selected.length} selected</span>
          <Button type="button" size="sm" onClick={() => runBulk("approve")} className="bg-emerald-600 hover:bg-emerald-700 font-bold">Approve</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => runBulk("reject")} className="font-bold">Reject</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => runBulk("feature")} className="font-bold">Feature</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => runBulk("unfeature")} className="font-bold">Unfeature</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => runBulk("delete")} className="font-bold text-red-600 border-red-200 hover:bg-red-50">Delete</Button>
        </div>
      )}

      <div className="space-y-3">
        {reviews.length === 0 && <div className="text-center text-muted-foreground py-10">No reviews</div>}
        {reviews.map((r, i) => (
          <Card key={r.review_id} className="dashboard-card border-none hover:shadow-md transition-shadow">
            <CardContent className="p-5 flex flex-wrap items-center gap-4 justify-between">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <Checkbox checked={selected.includes(r.review_id)} onCheckedChange={() => toggleSelected(r.review_id)} />
                <div className="min-w-0 cursor-pointer" onClick={() => setActiveReviewId(r.review_id)}>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="font-display font-bold text-lg truncate">{r.name}</div>
                    {r.featured && <Badge variant="outline" className="text-2xs font-bold uppercase">Featured</Badge>}
                  </div>
                  <div className="text-sm text-muted-foreground font-semibold truncate">{r.organization || "—"} · {r.rating}★</div>
                  <div className="text-xs text-muted-foreground mt-1 truncate max-w-md">{r.review}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {status === "approved" && (
                  <div className="flex flex-col gap-0.5">
                    <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="disabled:opacity-30">
                      <ArrowUp className="w-3.5 h-3.5" />
                    </button>
                    <button type="button" onClick={() => move(i, 1)} disabled={i === reviews.length - 1} className="disabled:opacity-30">
                      <ArrowDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
                <Badge className={`${STATUS_BADGE[r.status]} border-0 font-bold uppercase`}>{r.status}</Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <ReviewDetailDialog
        reviewId={activeReviewId}
        open={!!activeReviewId}
        onOpenChange={(v) => !v && setActiveReviewId(null)}
        onChanged={refreshAll}
      />
    </PageContainer>
  );
}
