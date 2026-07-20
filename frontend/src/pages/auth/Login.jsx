import React, { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { ArrowRight, Phone, Mail, Loader2 } from "lucide-react";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import Logo from "@/components/shared/Logo";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, otpRequest, otpVerify } = useAuth();
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  useEffect(() => {
    // Set by the axios interceptor (see lib/api.js) when an already-logged-in
    // session gets 401'd because the account was deactivated mid-session.
    const msg = sessionStorage.getItem("cb_auth_message");
    if (msg) {
      sessionStorage.removeItem("cb_auth_message");
      toast.error(msg);
    }
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(email, password);
      toast.success(`Welcome back, ${u.name}`);
      navigate(u.role === "admin" ? "/admin" : u.role === "vendor" ? "/vendor" : "/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  };

  const handleOtpSend = async () => {
    if (!phone.match(/^\d{10}$/)) {
      toast.error("Enter a valid 10-digit phone number");
      return;
    }
    setLoading(true);
    try {
      await otpRequest(phone);
      setOtpSent(true);
      toast.success("OTP sent");
    } catch (e) {
      toast.error("Could not send OTP");
    } finally { setLoading(false); }
  };

  const handleOtpVerify = async () => {
    setLoading(true);
    try {
      const u = await otpVerify(phone, otp);
      toast.success(`Welcome, ${u.name}`);
      navigate("/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invalid OTP");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-background grid grid-cols-1 lg:grid-cols-2">
      <div className="hidden lg:block relative bg-primary overflow-hidden">
        <div className="absolute inset-0 cb-grain opacity-30"></div>
        <img src="https://images.unsplash.com/photo-1593115057322-e94b77572f20?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" className="absolute inset-0 w-full h-full object-cover opacity-30" alt="" />
        <div className="relative h-full p-12 flex flex-col justify-between text-white">
          <Link to="/" className="flex flex-col mb-1" data-testid="login-logo">
            {/* Wordmark variant, not the image lockup — the approved asset
                is black/orange text on a transparent background and would
                be unreadable on this dark bg-primary hero panel. */}
            <Logo variant="wordmark" clickable={false} />
            <div className="text-2xs uppercase tracking-[0.2em] text-white/70 font-bold mt-0.5">India</div>
          </Link>
          <div className="space-y-6 max-w-md">
            <h1 className="font-display font-black text-5xl tracking-tighter leading-[0.95]">
              India's largest legal services marketplace.
            </h1>
            <p className="text-white/70 text-lg font-medium">
              Photocopy. Print. E-File. Notarize. Bind. Deliver. Every court chore — one login.
            </p>
            <div className="flex items-center gap-4 text-sm text-white/80 font-semibold">
              <div>1,200+ vendors</div>
              <div className="w-1 h-1 bg-white/40 rounded-full"></div>
              <div>850+ courts</div>
              <div className="w-1 h-1 bg-white/40 rounded-full"></div>
              <div>28 states</div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6 lg:p-12">
        <Card className="w-full max-w-md border-none shadow-none">
          <CardContent className="p-0">
            <div className="mb-8">
              <div className="cb-overline text-accent">Welcome back</div>
              <h2 className="font-display font-black text-4xl mt-2 tracking-tighter">Sign in to CourtBazaar™</h2>
              <p className="text-muted-foreground mt-2 font-medium">No account? <Link to="/register" className="text-accent font-bold hover:underline" data-testid="login-go-register">Create one</Link></p>
            </div>

            <Tabs defaultValue="email">
              <TabsList className="grid w-full grid-cols-2 mb-6" data-testid="login-tabs">
                <TabsTrigger value="email" data-testid="login-tab-email"><Mail className="w-4 h-4 mr-2" /> Email</TabsTrigger>
                <TabsTrigger value="phone" data-testid="login-tab-phone"><Phone className="w-4 h-4 mr-2" /> Phone OTP</TabsTrigger>
              </TabsList>

              <TabsContent value="email">
                <form onSubmit={handleLogin} className="space-y-4">
                  <div>
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email-input" />
                  </div>
                  <div>
                    <Label htmlFor="password">Password</Label>
                    <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password-input" />
                  </div>
                  <Button type="submit" disabled={loading} className="w-full bg-primary hover:bg-primary/90 h-12 font-bold" data-testid="login-submit-btn">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Sign in <ArrowRight className="w-4 h-4 ml-2" /></>}
                  </Button>
                </form>
              </TabsContent>

              <TabsContent value="phone">
                {!otpSent ? (
                  <div className="space-y-4">
                    <div>
                      <Label>Phone Number</Label>
                      <div className="flex gap-2">
                        <div className="px-3 flex items-center bg-secondary rounded-md text-sm font-semibold">+91</div>
                        <Input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))} placeholder="9876543210" data-testid="login-phone-input" />
                      </div>
                    </div>
                    <Button onClick={handleOtpSend} disabled={loading} className="w-full bg-primary h-12 font-bold" data-testid="login-otp-send-btn">
                      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send OTP"}
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <Label>Enter OTP sent to +91 {phone}</Label>
                      <div className="mt-2 flex justify-center">
                        <InputOTP maxLength={6} value={otp} onChange={setOtp} data-testid="login-otp-input">
                          <InputOTPGroup>
                            {[0,1,2,3,4,5].map(i => <InputOTPSlot key={i} index={i} />)}
                          </InputOTPGroup>
                        </InputOTP>
                      </div>
                    </div>
                    <Button onClick={handleOtpVerify} disabled={loading || otp.length < 6} className="w-full bg-primary h-12 font-bold" data-testid="login-otp-verify-btn">
                      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify & Continue"}
                    </Button>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
