import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, LifeBuoy } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import { createSupportTicket } from "@/lib/supportTicketsApi";

const CATEGORIES = [
  { value: "order", label: "Order Issue" },
  { value: "payment", label: "Payment" },
  { value: "account", label: "Account" },
  { value: "technical", label: "Technical Issue" },
  { value: "feature_request", label: "Feature Request / Change" },
  { value: "other", label: "Other" },
];

const emptyForm = { name: "", email: "", phone: "", category: "", subject: "", message: "", orderId: "" };

export default function SupportTicketModal({ open, onOpenChange }) {
  const { user } = useAuth();
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [ticket, setTicket] = useState(null); // { ticket_id } once submitted

  // Prefill from the logged-in account (if any) each time the dialog opens
  // fresh — a signed-in user shouldn't have to retype what we already know.
  useEffect(() => {
    if (open && !ticket) {
      setForm((prev) => ({ ...prev, name: prev.name || user?.name || "", email: prev.email || user?.email || "", phone: prev.phone || user?.phone || "" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const reset = () => {
    setForm(emptyForm);
    setTicket(null);
  };

  const handleOpenChange = (next) => {
    onOpenChange(next);
    if (!next) setTimeout(reset, 200); // wait out the close animation before clearing
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.category || !form.subject.trim() || !form.message.trim()) {
      toast.error("Please fill in all required fields.");
      return;
    }
    setSubmitting(true);
    try {
      const { ticket_id } = await createSupportTicket({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        category: form.category,
        subject: form.subject.trim(),
        message: form.message.trim(),
        orderId: form.orderId.trim() || undefined,
      });
      setTicket({ ticket_id });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "We couldn't raise your ticket. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[calc(100%-1.5rem)] sm:w-full sm:max-w-md max-h-[90dvh] overflow-y-auto cb-scroll">
        {ticket ? (
          <div className="flex flex-col items-center text-center py-6 px-2">
            <div className="w-16 h-16 rounded-full bg-emerald-50 flex items-center justify-center mb-5">
              <CheckCircle2 className="w-9 h-9 text-emerald-500" strokeWidth={1.75} />
            </div>
            <h3 className="font-display font-bold text-2xl mb-2">Ticket Raised</h3>
            <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
              Your support ticket <b className="text-foreground">#{ticket.ticket_id}</b> has been logged. Our
              team will get back to you at <b className="text-foreground">{form.email}</b> shortly.
            </p>
            <p className="text-xs text-muted-foreground/80 max-w-sm mt-2">
              Please quote this Ticket ID in any follow-up communication.
            </p>
            <Button type="button" onClick={() => handleOpenChange(false)} className="bg-accent hover:bg-accent/90 text-white font-bold px-8 mt-6">
              Done
            </Button>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="font-display text-xl flex items-center gap-2">
                <LifeBuoy className="w-5 h-5 text-accent" /> Raise a Support Ticket
              </DialogTitle>
              <DialogDescription>
                Tell us what's going on — a bug, a change you'd like, or anything else. We'll follow up by email.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-semibold text-foreground block mb-1.5">Full Name</label>
                  <Input placeholder="Your name" value={form.name} onChange={set("name")} required />
                </div>
                <div>
                  <label className="text-sm font-semibold text-foreground block mb-1.5">Email</label>
                  <Input type="email" placeholder="you@example.com" value={form.email} onChange={set("email")} required />
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-semibold text-foreground block mb-1.5">Phone (optional)</label>
                  <Input placeholder="10-digit mobile number" value={form.phone} onChange={set("phone")} />
                </div>
                <div>
                  <label className="text-sm font-semibold text-foreground block mb-1.5">Category</label>
                  <Select value={form.category} onValueChange={(v) => setForm((prev) => ({ ...prev, category: v }))}>
                    <SelectTrigger><SelectValue placeholder="Choose a category" /></SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <label className="text-sm font-semibold text-foreground block mb-1.5">Order ID (optional)</label>
                <Input placeholder="If this is about a specific order" value={form.orderId} onChange={set("orderId")} />
              </div>

              <div>
                <label className="text-sm font-semibold text-foreground block mb-1.5">Subject</label>
                <Input placeholder="A short summary of your request" value={form.subject} onChange={set("subject")} required />
              </div>

              <div>
                <label className="text-sm font-semibold text-foreground block mb-1.5">Message</label>
                <Textarea placeholder="Describe the issue, or what you'd like changed..." rows={4} value={form.message} onChange={set("message")} required />
              </div>

              <DialogFooter className="pt-1">
                <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold w-full sm:w-auto">
                  {submitting ? "Submitting..." : "Raise Ticket"}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
