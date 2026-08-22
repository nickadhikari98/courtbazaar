import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty, TableLoading,
} from "@/components/ui/table";
import { Briefcase, X, Plus, Trash2, Star, CheckCircle2, Clock, ArrowRight } from "lucide-react";
import {
  getPracticeProfile, updatePracticeProfile, listAvailabilitySlots,
  addAvailabilitySlot, removeAvailabilitySlot, getPracticePerformance,
} from "@/lib/practiceApi";
import { listHearingRequests } from "@/lib/hearingRequestsApi";
import { getCourt, searchCourts } from "@/lib/referenceDataApi";
import { formatINR } from "@/lib/api";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import HearingActivityPreview from "@/components/shared/HearingActivityPreview";
import CapabilitiesCard from "@/components/shared/CapabilitiesCard";
import StatGrid from "@/components/shared/StatGrid";
import Loading from "@/components/shared/Loading";
import { useAuth } from "@/context/AuthContext";
import {
  HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getViewerRole,
  isHearingActive, COMPLETED_HEARING_STATUSES, CLOSED_HEARING_STATUSES,
} from "@/lib/hearingLifecycle";
import {
  PRICING_SLOTS, PRICING_SLOT_LABELS, PRICING_COURT_TYPES, PRICING_COURT_TYPE_LABELS,
  PRICING_MINIMUMS, EXPERIENCE_BRACKETS,
} from "@/config/proxyCounselPricing";

const HEARING_TAB_LABELS = { active: "Active", completed: "Completed", cancelled: "Cancelled" };

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const KINDS = [
  { value: "recurring_weekly", label: "Weekly recurring" },
  { value: "custom_date", label: "Custom date" },
  { value: "holiday_block", label: "Holiday (blocked)" },
  { value: "emergency_unavailable", label: "Emergency unavailable" },
];

/* Simple chip-input for a string[] field (practice areas / courts /
   languages) — local to this page, not promoted to a global ui primitive
   since nothing else needs a tag input yet. */
function TagInput({ label, value, onChange, placeholder }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  return (
    <div>
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5 mb-2 mt-1.5">
        {value.map((tag) => (
          <Badge key={tag} variant="outline" className="gap-1 font-semibold">
            {tag}
            <button type="button" onClick={() => onChange(value.filter((t) => t !== tag))}>
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        <Button type="button" variant="outline" onClick={add}><Plus className="w-4 h-4" /></Button>
      </div>
    </div>
  );
}

/* Bug fix: "Courts" used to be a free-text TagInput — a counsel could type
   "Gujarat High Court" and it would display fine everywhere (it's just
   shown as typed), but list_and_recommend/public_proxy_counsels filter
   proxy_counsel_profiles.courts by real court_id ($in a set of ids looked
   up from the courts collection), so free text never matched and the
   counsel silently never showed up when someone searched/selected that
   court. This picks real courts by name (searchCourts, same /courts?q=
   endpoint the public Court Directory uses) and stores court_id — display
   names for already-saved ids are resolved lazily below, so legacy
   free-text rows (pre-fix) still render as a removable chip instead of a
   raw id, they just won't match search until re-picked from here. */
function CourtPicker({ label, value, onChange }) {
  const [nameById, setNameById] = useState({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const missing = value.filter((id) => !(id in nameById));
    if (!missing.length) return;
    let cancelled = false;
    Promise.all(missing.map((id) => getCourt(id).then((c) => [id, c.name]).catch(() => [id, id])))
      .then((pairs) => { if (!cancelled) setNameById((prev) => ({ ...prev, ...Object.fromEntries(pairs) })); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when `value` gains an id we haven't resolved yet
  }, [value]);

  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return undefined; }
    const t = setTimeout(() => {
      searchCourts(query.trim()).then((list) => setResults(list.slice(0, 20))).catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  const add = (court) => {
    if (!value.includes(court.court_id)) {
      setNameById((prev) => ({ ...prev, [court.court_id]: court.name }));
      onChange([...value, court.court_id]);
    }
    setQuery("");
    setResults([]);
    setOpen(false);
  };
  const remove = (id) => onChange(value.filter((v) => v !== id));

  return (
    <div>
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5 mb-2 mt-1.5">
        {value.map((id) => (
          <Badge key={id} variant="outline" className="gap-1 font-semibold">
            {nameById[id] || id}
            <button type="button" onClick={() => remove(id)}>
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="relative">
        <Input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Search a court by name, e.g. Gujarat High Court"
          data-testid="courts-picker-search"
        />
        {open && results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full bg-white border border-border rounded-lg shadow-lg max-h-56 overflow-y-auto cb-scroll">
            {results.map((c) => (
              <button
                key={c.court_id} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => add(c)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-secondary flex items-center justify-between gap-2"
              >
                <span className="truncate">{c.name}</span>
                <span className="text-2xs text-muted-foreground uppercase flex-shrink-0">{c.type?.replace("_", " ")}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="text-2xs text-muted-foreground mt-1">Pick real courts from search — these are what a Counsel's court filter actually matches against.</p>
    </div>
  );
}

function ProfileTab({ profile, onSaved }) {
  const { user } = useAuth();
  const [form, setForm] = useState(profile);
  const [saving, setSaving] = useState(false);
  const [savingAvailability, setSavingAvailability] = useState(false);
  const [savingInstant, setSavingInstant] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setPricing = (courtType, slot, value) => {
    setForm((f) => ({
      ...f,
      pricing: { ...f.pricing, [courtType]: { ...(f.pricing?.[courtType] || {}), [slot]: value === "" ? undefined : Number(value) } },
    }));
  };

  const hasInvalidPricing = () => PRICING_COURT_TYPES.some((courtType) => PRICING_SLOTS.some((slot) => {
    const amount = form.pricing?.[courtType]?.[slot];
    return amount != null && amount < PRICING_MINIMUMS[courtType][slot];
  }));

  const save = async () => {
    for (const courtType of PRICING_COURT_TYPES) {
      for (const slot of PRICING_SLOTS) {
        const amount = form.pricing?.[courtType]?.[slot];
        const minimum = PRICING_MINIMUMS[courtType][slot];
        if (amount != null && amount < minimum) {
          toast.error(`${PRICING_COURT_TYPE_LABELS[courtType]} / ${PRICING_SLOT_LABELS[slot]} must be at least ₹${minimum}`);
          return;
        }
      }
    }
    setSaving(true);
    try {
      const updated = await updatePracticeProfile({
        practice_areas: form.practice_areas, courts: form.courts, languages: form.languages,
        experience_bracket: form.experience_bracket, education: form.education, bio: form.bio,
        office_address: form.office_address, fee_structure: form.fee_structure, pricing: form.pricing,
        availability_mode: form.availability_mode, instant_booking: form.instant_booking,
      });
      onSaved(updated);
      toast.success("Profile saved");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save profile");
    } finally {
      setSaving(false);
    }
  };

  // Toggle switches save on their own, immediately, via the inline "Save"
  // button beside them — not the big "Save profile" button below, which is
  // easy to miss after just flipping a switch and can be a scroll away.
  // Sends only the one field (the PUT is a partial update, exclude_unset on
  // the backend) so it can't accidentally persist unrelated in-progress edits
  // sitting elsewhere in the form.
  const saveToggle = async (key, setBusy) => {
    setBusy(true);
    try {
      const updated = await updatePracticeProfile({ [key]: form[key] });
      onSaved(updated);
      toast.success(key === "availability_mode" ? "Availability updated" : "Instant booking updated");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <CapabilitiesCard user={user} />
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 flex items-center justify-between gap-4">
          <div>
            <div className="font-display font-bold">Available for hearings</div>
            <p className="text-xs text-muted-foreground">Turn off if you're not taking new requests right now.</p>
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={!!form.availability_mode} onCheckedChange={(v) => set("availability_mode", v)} />
            <Button
              type="button" size="sm" onClick={() => saveToggle("availability_mode", setSavingAvailability)}
              disabled={savingAvailability}
              className={form.availability_mode
                ? "bg-accent hover:bg-accent/90 font-bold"
                : "bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold"}
            >
              Save
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 flex items-center justify-between gap-4">
          <div>
            <div className="font-display font-bold">Instant booking</div>
            <p className="text-xs text-muted-foreground">Skip manual accept for requests that match your availability.</p>
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={!!form.instant_booking} onCheckedChange={(v) => set("instant_booking", v)} />
            <Button
              type="button" size="sm" onClick={() => saveToggle("instant_booking", setSavingInstant)}
              disabled={savingInstant}
              className={form.instant_booking
                ? "bg-accent hover:bg-accent/90 font-bold"
                : "bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold"}
            >
              Save
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <span className="font-display font-bold">Verification</span>
            <Badge className={form.kyc_status === "approved" ? "bg-emerald-100 text-emerald-700 border-0" : "bg-amber-100 text-amber-700 border-0"}>
              {form.kyc_status}
            </Badge>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Total Years of Practice</Label>
              <Select value={form.experience_bracket || undefined} onValueChange={(v) => set("experience_bracket", v)}>
                <SelectTrigger data-testid="experience-bracket"><SelectValue placeholder="Select range" /></SelectTrigger>
                <SelectContent>
                  {EXPERIENCE_BRACKETS.map((b) => <SelectItem key={b.key} value={b.key}>{b.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Education</Label>
              <Input value={form.education || ""} onChange={(e) => set("education", e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Bio</Label>
            <Textarea rows={3} value={form.bio || ""} onChange={(e) => set("bio", e.target.value)} />
          </div>
          <div>
            <Label>Office address</Label>
            <Input value={form.office_address || ""} onChange={(e) => set("office_address", e.target.value)} />
          </div>
          <div>
            <Label>Fee structure</Label>
            <Textarea rows={2} value={form.fee_structure || ""} onChange={(e) => set("fee_structure", e.target.value)} placeholder="e.g. ₹2,000 per appearance" />
          </div>
          <TagInput label="Practice areas" value={form.practice_areas || []} onChange={(v) => set("practice_areas", v)} placeholder="e.g. Civil, Criminal" />
          <CourtPicker label="Courts" value={form.courts || []} onChange={(v) => set("courts", v)} />
          <TagInput label="Languages" value={form.languages || []} onChange={(v) => set("languages", v)} placeholder="e.g. Hindi, English" />
          <Button type="button" onClick={save} disabled={saving} className="bg-accent hover:bg-accent/90 font-bold">Save profile</Button>
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          <div>
            <div className="font-display font-bold">Availability & Pricing</div>
            <p className="text-xs text-muted-foreground mt-0.5">Set your own price per slot — never below the platform minimum shown under each field. Leave a slot blank if you don't take that kind of work.</p>
          </div>
          {PRICING_COURT_TYPES.map((courtType) => (
            <div key={courtType}>
              <div className="text-sm font-bold mb-2">{PRICING_COURT_TYPE_LABELS[courtType]}</div>
              <div className="grid sm:grid-cols-3 gap-3">
                {PRICING_SLOTS.map((slot) => {
                  const minimum = PRICING_MINIMUMS[courtType][slot];
                  const amount = form.pricing?.[courtType]?.[slot];
                  const belowMin = amount != null && amount < minimum;
                  return (
                    <div key={slot}>
                      <Label>{PRICING_SLOT_LABELS[slot]}</Label>
                      <Input
                        type="number" min={minimum}
                        value={amount ?? ""}
                        onChange={(e) => setPricing(courtType, slot, e.target.value)}
                        placeholder={`Min ₹${minimum}`}
                        onWheel={(e) => e.target.blur()}
                        className={belowMin ? "border-red-500 focus-visible:ring-red-500" : undefined}
                        aria-invalid={belowMin || undefined}
                        data-testid={`pricing-${courtType}-${slot}`}
                      />
                      {belowMin ? (
                        <p className="text-2xs text-red-600 mt-0.5">Must be at least ₹{minimum}</p>
                      ) : (
                        <p className="text-2xs text-muted-foreground mt-0.5">Min ₹{minimum}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          <Button type="button" onClick={save} disabled={saving || hasInvalidPricing()} className="bg-accent hover:bg-accent/90 font-bold">Save profile</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function AvailabilityTab() {
  const [slots, setSlots] = useState(null);
  const [kind, setKind] = useState("recurring_weekly");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [date, setDate] = useState("");
  const [courtId, setCourtId] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");

  const load = () => listAvailabilitySlots().then(setSlots);
  useEffect(() => { load(); }, []);

  const add = async () => {
    try {
      await addAvailabilitySlot({
        kind,
        day_of_week: kind === "recurring_weekly" ? dayOfWeek : undefined,
        date: kind !== "recurring_weekly" ? date : undefined,
        court_id: courtId || undefined,
        start_time: startTime || undefined,
        end_time: endTime || undefined,
      });
      toast.success("Availability added");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not add slot");
    }
  };

  const remove = async (slotId) => {
    await removeAvailabilitySlot(slotId);
    load();
  };

  return (
    <div className="space-y-4">
      <Card className="dashboard-card border-none">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">Add availability</div>
          <div className="grid sm:grid-cols-2 gap-3 mb-3">
            <div>
              <Label>Kind</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {kind === "recurring_weekly" ? (
              <div>
                <Label>Day of week</Label>
                <Select value={String(dayOfWeek)} onValueChange={(v) => setDayOfWeek(Number(v))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DAYS.map((d, i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div>
                <Label>Date</Label>
                <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </div>
            )}
            <div>
              <Label>Court (optional — blank = any court)</Label>
              <Input value={courtId} onChange={(e) => setCourtId(e.target.value)} placeholder="e.g. Delhi High Court" />
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <Label>From</Label>
                <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
              </div>
              <div className="flex-1">
                <Label>To</Label>
                <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
              </div>
            </div>
          </div>
          <Button type="button" onClick={add} className="bg-accent hover:bg-accent/90 font-bold">
            <Plus className="w-4 h-4 mr-1.5" /> Add
          </Button>
        </CardContent>
      </Card>

      <div className="rounded-xl border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kind</TableHead>
              <TableHead>When</TableHead>
              <TableHead>Court</TableHead>
              <TableHead>Time</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {slots === null && <TableLoading colSpan={5} />}
            {slots?.length === 0 && <TableEmpty colSpan={5}>No availability set yet</TableEmpty>}
            {slots?.map((s) => (
              <TableRow key={s.slot_id}>
                <TableCell><Badge variant="outline" className="text-2xs uppercase">{s.kind.replace(/_/g, " ")}</Badge></TableCell>
                <TableCell>{s.kind === "recurring_weekly" ? DAYS[s.day_of_week] : s.date}</TableCell>
                <TableCell>{s.court_id || "Any"}</TableCell>
                <TableCell>{s.start_time && s.end_time ? `${s.start_time}–${s.end_time}` : "Full day"}</TableCell>
                <TableCell>
                  <button type="button" onClick={() => remove(s.slot_id)} className="text-muted-foreground hover:text-red-600">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function PerformanceTab() {
  const [perf, setPerf] = useState(null);
  useEffect(() => { getPracticePerformance().then(setPerf); }, []);
  if (!perf) return <Loading />;

  const stats = [
    { label: "Rating", value: perf.rating || "—", icon: Star, color: "bg-amber-100 text-amber-700" },
    { label: "Cases Completed", value: perf.cases_completed, icon: CheckCircle2, color: "bg-emerald-100 text-emerald-700" },
    { label: "Upcoming Hearings", value: perf.upcoming_hearings, icon: Clock, color: "bg-accent/10 text-accent" },
    { label: "Pending Requests", value: perf.pending_requests, icon: Briefcase, color: "bg-blue-100 text-blue-700" },
  ];
  return <StatGrid stats={stats} />;
}

function HearingsTab() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  // Negotiation Module: a hearing targeted at this advocate is invisible
  // everywhere else until it reaches "broadcast" (post-payment) — this is
  // the one place the pending-negotiation window (see hearings.py's
  // list_hearing_requests) actually surfaces to them.
  const negotiating = hearings?.filter((h) => h.target_advocate_id === user?.user_id
    && ["requested", "payment_pending"].includes(h.status)) || [];
  const open = hearings?.filter((h) => h.status === "broadcast" && h.requesting_user_id !== user?.user_id) || [];
  const mine = hearings?.filter((h) => h.proxy_counsel_user_id === user?.user_id) || [];
  // Assigned hearings run the full lifecycle (including cancel/expire), so
  // unlike Negotiation/Open Requests above this needs its own Active/
  // Completed/Cancelled split rather than one flat list.
  const mineTabs = {
    active: mine.filter(isHearingActive),
    completed: mine.filter((h) => COMPLETED_HEARING_STATUSES.includes(h.status)),
    cancelled: mine.filter((h) => CLOSED_HEARING_STATUSES.includes(h.status)),
  };

  const renderCard = (h, onClick) => (
    <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={onClick}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="font-display font-bold text-sm">{h.court_id}</div>
            <div className="text-xs text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
          </div>
          <Badge className={`${HEARING_STATUS_BADGE_COLOR[h.status] || ""} border-0 font-bold uppercase text-2xs`}>
            {roleAwareStatusLabel(h, getViewerRole(h, user?.user_id))}
          </Badge>
        </div>
        <HearingActivityPreview hearing={h} />
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      {/* Pending Offers — hiring-flow UX rewrite: a counsel should never have
          to hunt through notifications to find work waiting on them. This is
          the one place a targeted, pre-payment hearing (see hearings.py's
          list_hearing_requests — invisible everywhere else until "broadcast")
          actually surfaces in their own workspace. Each card shows only what's
          needed to recognize the request at a glance; the actual Accept/
          Reject/Negotiate actions live on the (also redesigned) Negotiation
          page — one "Respond to Offer" CTA here, not a second copy of those
          three buttons competing for space on this list. */}
      {!!negotiating.length && (
        <div>
          <div className="font-display font-bold mb-2">Pending Offers</div>
          <p className="text-xs text-muted-foreground mb-3">A client has requested you directly — respond to move forward.</p>
          <div className="grid sm:grid-cols-2 gap-3">
            {negotiating.map((h) => (
              <Card key={h.hearing_id} className="border-l-4 border-l-accent shadow-sm" data-testid={`pending-offer-${h.hearing_id}`}>
                <CardContent className="p-4">
                  <div className="font-display font-bold text-sm truncate">{h.request_details?.common?.case_title || h.court_id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{h.request_details?.common?.court_name || h.court_id} · {h.hearing_date}</div>
                  {h.fee != null && <div className="text-lg font-display font-bold mt-2">{formatINR(h.fee)}</div>}
                  <Button
                    type="button" size="sm" className="w-full font-bold bg-accent hover:bg-accent/90 mt-3"
                    onClick={() => navigate(`/hearing-requests/${h.hearing_id}/negotiate`)}
                    data-testid={`respond-to-offer-${h.hearing_id}`}
                  >
                    Respond to Offer <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="font-display font-bold mb-2">Open Requests</div>
        {hearings === null && <Loading size="sm" />}
        {hearings && open.length === 0 && <p className="text-sm text-muted-foreground">No open requests right now.</p>}
        <div className="space-y-2">{open.map((h) => renderCard(h, () => setActiveId(h.hearing_id)))}</div>
      </div>
      <div>
        <div className="font-display font-bold mb-2">My Hearings</div>
        {hearings === null && <Loading size="sm" />}
        {hearings && mine.length === 0 && <p className="text-sm text-muted-foreground">Nothing accepted yet.</p>}
        {hearings && mine.length > 0 && (
          <Tabs defaultValue="active">
            <TabsList data-testid="my-hearings-tabs">
              {Object.entries(mineTabs).map(([key, list]) => (
                <TabsTrigger key={key} value={key} data-testid={`tab-my-${key}`}>
                  {HEARING_TAB_LABELS[key]} ({list.length})
                </TabsTrigger>
              ))}
            </TabsList>
            {Object.entries(mineTabs).map(([key, list]) => (
              <TabsContent value={key} key={key} className="mt-3 space-y-2">
                {list.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No {HEARING_TAB_LABELS[key].toLowerCase()} hearings.</p>
                ) : list.map((h) => renderCard(h, () => setActiveId(h.hearing_id)))}
              </TabsContent>
            ))}
          </Tabs>
        )}
      </div>
      <HearingDetailDialog hearingId={activeId} open={!!activeId} onOpenChange={(v) => !v && setActiveId(null)} onChanged={load} />
    </div>
  );
}

export default function Practice() {
  const [profile, setProfile] = useState(null);

  useEffect(() => { getPracticeProfile().then(setProfile); }, []);

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader eyebrow="My Practice" eyebrowIcon={Briefcase} title="Your practice, in one place" />
      <Tabs defaultValue="profile" className="mt-6">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="availability">Availability</TabsTrigger>
          <TabsTrigger value="hearings">Hearings</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="mt-4">
          {profile ? <ProfileTab profile={profile} onSaved={setProfile} /> : <Loading />}
        </TabsContent>
        <TabsContent value="availability" className="mt-4">
          <AvailabilityTab />
        </TabsContent>
        <TabsContent value="hearings" className="mt-4">
          <HearingsTab />
        </TabsContent>
        <TabsContent value="performance" className="mt-4">
          <PerformanceTab />
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
