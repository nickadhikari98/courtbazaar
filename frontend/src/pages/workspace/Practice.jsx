import React, { useEffect, useState } from "react";
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
import { Briefcase, X, Plus, Trash2, Star, CheckCircle2, Clock } from "lucide-react";
import {
  getPracticeProfile, updatePracticeProfile, listAvailabilitySlots,
  addAvailabilitySlot, removeAvailabilitySlot, getPracticePerformance,
} from "@/lib/practiceApi";
import { listHearingRequests } from "@/lib/hearingRequestsApi";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import CapabilitiesCard from "@/components/shared/CapabilitiesCard";
import StatGrid from "@/components/shared/StatGrid";
import { useAuth } from "@/context/AuthContext";

const HEARING_STATUS_BADGE = {
  broadcast: "bg-amber-100 text-amber-700",
  accepted: "bg-blue-100 text-blue-700",
  payment_pending: "bg-amber-100 text-amber-700",
  documents_shared: "bg-blue-100 text-blue-700",
  preparation: "bg-blue-100 text-blue-700",
  hearing_scheduled: "bg-blue-100 text-blue-700",
  hearing_completed: "bg-indigo-100 text-indigo-700",
  verification_pending: "bg-amber-100 text-amber-700",
  verified: "bg-emerald-100 text-emerald-700",
  completed: "bg-emerald-100 text-emerald-700",
  rated: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
  disputed: "bg-red-100 text-red-700",
  expired: "bg-slate-100 text-slate-600",
};

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

function ProfileTab({ profile, onSaved }) {
  const { user } = useAuth();
  const [form, setForm] = useState(profile);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const updated = await updatePracticeProfile({
        practice_areas: form.practice_areas, courts: form.courts, languages: form.languages,
        experience_years: form.experience_years, education: form.education, bio: form.bio,
        office_address: form.office_address, fee_structure: form.fee_structure,
        availability_mode: form.availability_mode, instant_booking: form.instant_booking,
      });
      onSaved(updated);
      toast.success("Profile saved");
    } catch {
      toast.error("Could not save profile");
    } finally {
      setSaving(false);
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
          <Switch checked={!!form.availability_mode} onCheckedChange={(v) => set("availability_mode", v)} />
        </CardContent>
      </Card>
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 flex items-center justify-between gap-4">
          <div>
            <div className="font-display font-bold">Instant booking</div>
            <p className="text-xs text-muted-foreground">Skip manual accept for requests that match your availability.</p>
          </div>
          <Switch checked={!!form.instant_booking} onCheckedChange={(v) => set("instant_booking", v)} />
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
              <Label>Years of experience</Label>
              <Input type="number" value={form.experience_years || ""} onChange={(e) => set("experience_years", Number(e.target.value))} />
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
          <TagInput label="Courts" value={form.courts || []} onChange={(v) => set("courts", v)} placeholder="e.g. Delhi High Court" />
          <TagInput label="Languages" value={form.languages || []} onChange={(v) => set("languages", v)} placeholder="e.g. Hindi, English" />
          <Button type="button" onClick={save} disabled={saving} className="bg-accent hover:bg-accent/90 font-bold">Save profile</Button>
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
  if (!perf) return <div className="text-center text-muted-foreground py-10">Loading…</div>;

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
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  const open = hearings?.filter((h) => h.status === "broadcast" && h.requesting_user_id !== user?.user_id) || [];
  const mine = hearings?.filter((h) => h.proxy_counsel_user_id === user?.user_id) || [];

  const renderCard = (h) => (
    <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveId(h.hearing_id)}>
      <CardContent className="p-4 flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="font-display font-bold text-sm">{h.court_id}</div>
          <div className="text-xs text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
        </div>
        <Badge className={`${HEARING_STATUS_BADGE[h.status] || ""} border-0 font-bold uppercase text-2xs`}>{h.status.replace(/_/g, " ")}</Badge>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="font-display font-bold mb-2">Open Requests</div>
        {hearings === null && <div className="text-center text-muted-foreground py-6 text-sm">Loading…</div>}
        {hearings && open.length === 0 && <p className="text-sm text-muted-foreground">No open requests right now.</p>}
        <div className="space-y-2">{open.map(renderCard)}</div>
      </div>
      <div>
        <div className="font-display font-bold mb-2">My Hearings</div>
        {hearings && mine.length === 0 && <p className="text-sm text-muted-foreground">Nothing accepted yet.</p>}
        <div className="space-y-2">{mine.map(renderCard)}</div>
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
          {profile ? <ProfileTab profile={profile} onSaved={setProfile} /> : <div className="text-center text-muted-foreground py-10">Loading…</div>}
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
