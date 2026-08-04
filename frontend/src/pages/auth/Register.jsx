import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { ArrowRight, Loader2, ShieldCheck, Eye, EyeOff } from "lucide-react";
import Logo from "@/components/shared/Logo";
import GoogleAuthButton from "@/components/shared/GoogleAuthButton";
import RoleSelectModal from "@/components/landing/join/RoleSelectModal";
import { vendorSections } from "@/components/landing/join/roleFormData";

// Vendor accounts are admin-vetted via the "Join as Vendor" lead pipeline
// (leads.py), not created directly here — see the matching
// SELF_REGISTER_BLOCKED_ROLES guard on the backend's /auth/register. This
// reuses the exact same modal/form the landing page's UtilityBar opens, just
// pre-scoped to the one role, so applying here and applying from the
// homepage go through identical logic.
const VENDOR_JOIN_ROLES = [{ key: "vendor", label: "Join as Vendor", icon: ShieldCheck, description: "Printing, photocopy & scanning services" }];
const VENDOR_JOIN_FORMS = {
  vendor: { title: "Join as Printing Vendor", description: "Partner with CourtBazaar™ and grow your business.", sections: vendorSections },
};

export default function Register() {
  const navigate = useNavigate();
  const { register, googleLogin, googleOAuthEnabled } = useAuth();
  const [loading, setLoading] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", password: "", role: "advocate" });
  const [vendorJoinOpen, setVendorJoinOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const isVendorRole = form.role === "vendor";

  const submit = async (e) => {
    e.preventDefault();
    if (!agreedToTerms || isVendorRole) return;
    setLoading(true);
    try {
      await register(form);
      toast.success("Account created. Welcome to CourtBazaar™!");
      navigate("/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Registration failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 max-w-6xl w-full items-center">
        <div className="hidden lg:block">
          <Logo size="lg" className="mb-10" data-testid="register-logo" />
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
          <CardContent className="p-6 sm:p-8">
            <div className="cb-overline text-accent">Sign up</div>
            <h2 className="font-display font-black text-3xl mt-1 tracking-tighter">Create your account</h2>
            <p className="text-muted-foreground mt-1 text-sm">Already have one? <Link to="/login" className="text-accent font-bold hover:underline" data-testid="register-go-login">Sign in</Link></p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
              {!isVendorRole && (
                <div>
                  <Label>Password</Label>
                  <div className="relative">
                    <Input
                      type={showPassword ? "text" : "password"}
                      value={form.password}
                      onChange={(e) => setForm({...form, password: e.target.value})}
                      required
                      minLength={6}
                      placeholder="Min 6 chars"
                      className="pr-10"
                      data-testid="register-password-input"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      data-testid="register-password-toggle"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              )}
              <div>
                <Label>I am a…</Label>
                <Select value={form.role} onValueChange={(v) => setForm({...form, role: v})}>
                  <SelectTrigger data-testid="register-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="advocate">Advocate</SelectItem>
                    {/* <SelectItem value="law_firm">Law Firm</SelectItem> */}
                    <SelectItem value="vendor">Vendor / Print Shop</SelectItem>
                    {/* <SelectItem value="legal_typist">Legal Typist</SelectItem> */}
                    {/* <SelectItem value="notary">Notary Partner</SelectItem> */}
                    <SelectItem value="delivery_partner">Delivery Partner</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {isVendorRole ? (
                <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 text-sm">
                  <p className="font-bold text-foreground">Vendor accounts are reviewed before activation.</p>
                  <p className="text-muted-foreground mt-1">
                    Vendors join through our application form — our team verifies every vendor before granting
                    access. Approved applicants receive their login details by email.
                  </p>
                  <Button
                    type="button"
                    onClick={() => setVendorJoinOpen(true)}
                    className="w-full mt-3 bg-primary hover:bg-primary/90 font-bold"
                    data-testid="register-vendor-apply-btn"
                  >
                    Open Vendor Application <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              ) : (
                <>
                  <div className="flex items-start gap-2.5">
                    <Checkbox
                      id="agree-terms"
                      checked={agreedToTerms}
                      onCheckedChange={(v) => setAgreedToTerms(v === true)}
                      className="mt-0.5"
                      data-testid="register-agree-terms"
                    />
                    <label htmlFor="agree-terms" className="text-sm text-muted-foreground leading-relaxed cursor-pointer">
                      I have read and agree to the{" "}
                      <Link to="/legal/terms" target="_blank" rel="noopener noreferrer" className="text-accent font-semibold hover:underline">
                        Terms
                      </Link>
                      ,{" "}
                      <Link to="/legal/privacy" target="_blank" rel="noopener noreferrer" className="text-accent font-semibold hover:underline">
                        Privacy Policy
                      </Link>
                      , and{" "}
                      <Link to="/legal/refund" target="_blank" rel="noopener noreferrer" className="text-accent font-semibold hover:underline">
                        Refund Policy
                      </Link>
                      .
                    </label>
                  </div>
                  <Button type="submit" disabled={loading || !agreedToTerms} className="w-full bg-primary hover:bg-primary/90 h-12 font-bold" data-testid="register-submit-btn">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Create account <ArrowRight className="w-4 h-4 ml-2" /></>}
                  </Button>
                </>
              )}
            </form>

            {googleOAuthEnabled && (
              <>
                <div className="flex items-center gap-3 my-6">
                  <div className="h-px flex-1 bg-border" />
                  <span className="text-2xs uppercase tracking-wide font-bold text-muted-foreground">Or continue with</span>
                  <div className="h-px flex-1 bg-border" />
                </div>
                <GoogleAuthButton onClick={() => googleLogin(form.role)} label="Continue with Google" />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <RoleSelectModal
        open={vendorJoinOpen}
        onOpenChange={setVendorJoinOpen}
        heading="Join as Vendor"
        subheading="Partner with CourtBazaar™ and grow your business."
        roles={VENDOR_JOIN_ROLES}
        forms={VENDOR_JOIN_FORMS}
      />
    </div>
  );
}
