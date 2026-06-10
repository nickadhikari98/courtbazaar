import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Scale, ArrowRight, Loader2 } from "lucide-react";

export default function Register() {
  const navigate = useNavigate();
  const { register, googleLogin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", password: "", role: "advocate" });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(form);
      toast.success("Account created. Welcome to CourtBazaar!");
      navigate(form.role === "vendor" ? "/vendor/onboard" : "/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Registration failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 max-w-6xl w-full items-center">
        <div className="hidden lg:block">
          <Link to="/" className="flex items-center gap-2.5 mb-10" data-testid="register-logo">
            <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
              <Scale className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-display font-black text-xl tracking-tight leading-none">CourtBazaar</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">India</div>
            </div>
          </Link>
          <h1 className="font-display font-black text-5xl tracking-tighter leading-[0.95]">
            Join 12,400+ advocates simplifying their court life.
          </h1>
          <p className="mt-5 text-lg text-muted-foreground font-medium">
            One dashboard for every court chore — from photocopy to e-filing across 850+ courts. Sign up free in 30 seconds.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-4">
            {["Free forever plan", "GST invoices", "Live tracking"].map((x) => (
              <div key={x} className="bento-card p-4">
                <div className="font-bold text-sm">{x}</div>
              </div>
            ))}
          </div>
        </div>

        <Card className="border-none shadow-xl">
          <CardContent className="p-8">
            <div className="cb-overline text-accent">Sign up</div>
            <h2 className="font-display font-black text-3xl mt-1 tracking-tighter">Create your account</h2>
            <p className="text-muted-foreground mt-1 text-sm">Already have one? <Link to="/login" className="text-accent font-bold hover:underline" data-testid="register-go-login">Sign in</Link></p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Full Name</Label>
                  <Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required placeholder="Adv. R. Kumar" data-testid="register-name-input" />
                </div>
                <div>
                  <Label>Phone</Label>
                  <Input value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value.replace(/\D/g, "").slice(0,10)})} placeholder="9876543210" data-testid="register-phone-input" />
                </div>
              </div>
              <div>
                <Label>Email</Label>
                <Input type="email" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})} required placeholder="you@chambers.in" data-testid="register-email-input" />
              </div>
              <div>
                <Label>Password</Label>
                <Input type="password" value={form.password} onChange={(e) => setForm({...form, password: e.target.value})} required minLength={6} placeholder="Min 6 chars" data-testid="register-password-input" />
              </div>
              <div>
                <Label>I am a…</Label>
                <Select value={form.role} onValueChange={(v) => setForm({...form, role: v})}>
                  <SelectTrigger data-testid="register-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="advocate">Advocate</SelectItem>
                    <SelectItem value="law_firm">Law Firm</SelectItem>
                    <SelectItem value="vendor">Vendor / Print Shop</SelectItem>
                    <SelectItem value="legal_typist">Legal Typist</SelectItem>
                    <SelectItem value="notary">Notary Partner</SelectItem>
                    <SelectItem value="delivery_partner">Delivery Partner</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={loading} className="w-full bg-primary hover:bg-primary/90 h-12 font-bold" data-testid="register-submit-btn">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Create account <ArrowRight className="w-4 h-4 ml-2" /></>}
              </Button>
            </form>

            <div className="relative my-5">
              <div className="cb-divider"></div>
              <span className="absolute inset-0 flex items-center justify-center text-xs"><span className="bg-card px-3 font-bold uppercase tracking-widest text-muted-foreground">or</span></span>
            </div>

            <Button variant="outline" className="w-full h-12 font-bold border-2" onClick={() => googleLogin(form.role)} data-testid="register-google-btn">
              <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24"><path fill="#4285f4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34a853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#fbbc05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#ea4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Continue with Google
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
