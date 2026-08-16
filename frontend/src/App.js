import React, { useEffect, Suspense, lazy } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import ScrollToTop from "@/components/ScrollToTop";
import Logo from "@/components/shared/Logo";
// AppLayout is the shared authenticated-app shell, not a route-level page —
// it loads for every authenticated visit regardless of which page is under
// it, so lazy-loading it separately would add a chunk with no benefit. See
// PRODUCT_DESIGN_SYSTEM.md §3.2 / DESIGN_SYSTEM_AUDIT.md §7.4.
import AppLayout from "@/components/layout/AppLayout";

// Every page below is route-level code-split via React.lazy(). Each page is
// its own chunk, fetched only when its route is visited — a marketing-page
// visitor no longer downloads the admin console or vendor dashboard bundles.
// See DESIGN_SYSTEM_AUDIT.md §7.4 for why this was the top performance
// recommendation (bundle was ~643KB gzipped, eagerly loaded in full for
// every visit before this change).
const Landing = lazy(() => import("@/pages/marketing/Landing"));
const Pricing = lazy(() => import("@/pages/marketing/Pricing"));
const VendorOnboarding = lazy(() => import("@/pages/marketing/VendorOnboarding"));
const About = lazy(() => import("@/pages/marketing/About"));
const Contact = lazy(() => import("@/pages/marketing/Contact"));
const Security = lazy(() => import("@/pages/marketing/Security"));
const Trust = lazy(() => import("@/pages/marketing/Trust"));
const LegalCenter = lazy(() => import("@/pages/legal/LegalCenter"));
const LegalDocument = lazy(() => import("@/pages/legal/LegalDocument"));
const Login = lazy(() => import("@/pages/auth/Login"));
const Register = lazy(() => import("@/pages/auth/Register"));
const SetPassword = lazy(() => import("@/pages/auth/SetPassword"));
const Dashboard = lazy(() => import("@/pages/customer/Dashboard"));
const HireProxyCounsel = lazy(() => import("@/pages/customer/HireProxyCounsel"));
const NegotiationModule = lazy(() => import("@/pages/customer/NegotiationModule"));
const HireCounsel = lazy(() => import("@/pages/customer/HireCounsel"));
const OrderWizard = lazy(() => import("@/pages/customer/OrderWizard"));
const OrderDetail = lazy(() => import("@/pages/customer/OrderDetail"));
const Orders = lazy(() => import("@/pages/customer/Orders"));
const Marketplace = lazy(() => import("@/pages/customer/Marketplace"));
const CourtDirectory = lazy(() => import("@/pages/customer/CourtDirectory"));
const AIAssistant = lazy(() => import("@/pages/customer/AIAssistant"));
const Wallet = lazy(() => import("@/pages/customer/Wallet"));
const Subscription = lazy(() => import("@/pages/customer/Subscription"));
const Profile = lazy(() => import("@/pages/customer/Profile"));
const BulkImport = lazy(() => import("@/pages/customer/BulkImport"));
const MyData = lazy(() => import("@/pages/customer/MyData"));
const FirmManagement = lazy(() => import("@/pages/customer/FirmManagement"));
const NotificationPrefs = lazy(() => import("@/pages/customer/NotificationPrefs"));
const Practice = lazy(() => import("@/pages/workspace/Practice"));
const Earnings = lazy(() => import("@/pages/workspace/Earnings"));
const Documents = lazy(() => import("@/pages/workspace/Documents"));
const Calendar = lazy(() => import("@/pages/workspace/Calendar"));
const Notifications = lazy(() => import("@/pages/workspace/Notifications"));
const VendorDashboard = lazy(() => import("@/pages/vendor/VendorDashboard"));
const VendorOnboard = lazy(() => import("@/pages/vendor/VendorOnboard"));
const VendorSettlements = lazy(() => import("@/pages/vendor/VendorSettlements"));
const AdminSettlements = lazy(() => import("@/pages/admin/AdminSettlements"));
const AdminHearingVerification = lazy(() => import("@/pages/admin/AdminHearingVerification"));
const AdminDashboard = lazy(() => import("@/pages/admin/AdminDashboard"));
const AdminVendors = lazy(() => import("@/pages/admin/AdminVendors"));
const AdminLeads = lazy(() => import("@/pages/admin/AdminLeads"));
const AdminReviews = lazy(() => import("@/pages/admin/AdminReviews"));
const AdminPricing = lazy(() => import("@/pages/admin/AdminPricing"));
const AdminUsers = lazy(() => import("@/pages/admin/AdminUsers"));
const AdminReconciliation = lazy(() => import("@/pages/admin/AdminReconciliation"));
const AdminWhatsAppTemplates = lazy(() => import("@/pages/admin/AdminWhatsAppTemplates"));
const AdminAuditLog = lazy(() => import("@/pages/admin/AdminAuditLog"));
const AdminLeaderboard = lazy(() => import("@/pages/admin/AdminLeaderboard"));
const SuperAdminConsole = lazy(() => import("@/pages/admin/SuperAdminConsole"));
const DeliveryHub = lazy(() => import("@/pages/delivery/DeliveryHub"));
const StenographerBooking = lazy(() => import("@/pages/special/StenographerBooking"));

/** Route-transition fallback — same spinner treatment already used by
 * ProtectedRoute's auth-loading state and AuthCallback below, so a lazy
 * chunk loading doesn't introduce a new visual pattern. */
function RouteLoadingFallback() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background">
      <Logo size="md" clickable={false} />
      <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
    </div>
  );
}

function AuthCallback() {
  const navigate = useNavigate();
  const { exchangeGoogleSession } = useAuth();
  const processed = React.useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = window.location.hash;
    const sessionId = hash.match(/session_id=([^&]+)/)?.[1];
    const role = new URLSearchParams(window.location.search).get("role") || "advocate";
    if (!sessionId) {
      navigate("/login");
      return;
    }
    exchangeGoogleSession(sessionId, role)
      .then(() => navigate("/dashboard", { replace: true }))
      .catch(() => navigate("/login"));
  }, [exchangeGoogleSession, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-muted-foreground font-medium">Signing you in…</p>
      </div>
    </div>
  );
}

// HireProxyCounsel.jsx is the one page in the app reachable without login
// (founder direction, 2026-08) — it picks its own shell (AppLayout vs
// MarketingLayout) based on auth state internally, so unlike every other
// protected page it can't just sit inside the <ProtectedRoute><AppLayout/></ProtectedRoute>
// group below. A logged-in user without the capability still gets bounced
// to /dashboard, same as before this change — only "no user at all" is new.
function HireProxyCounselRoute() {
  const { user, loading } = useAuth();
  if (loading) return <RouteLoadingFallback />;
  if (user && !user.capabilities?.includes("can_hire_proxy_counsel")) {
    return <Navigate to="/dashboard" replace />;
  }
  return <HireProxyCounsel />;
}

function ProtectedRoute({ children, roles, capabilities }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background">
        <Logo size="md" clickable={false} />
        <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  // Additive: a plain single-role account passes exactly as it always did
  // (user.role in roles); an account that has gained additional professional
  // profiles (active_roles, from get_current_user's capability computation)
  // also passes without its original `role` route access changing at all.
  if (roles && !roles.some((r) => user.role === r || user.active_roles?.includes(r))) {
    return <Navigate to="/dashboard" replace />;
  }
  if (capabilities && !capabilities.some((c) => user.capabilities?.includes(c))) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <>
    <ScrollToTop />
    <Suspense fallback={<RouteLoadingFallback />}>
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/set-password" element={<SetPassword />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/vendor-signup" element={<VendorOnboarding />} />
      <Route path="/about" element={<About />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/security" element={<Security />} />
      <Route path="/trust" element={<Trust />} />
      <Route path="/legal" element={<LegalCenter />} />
      <Route path="/legal/:slug" element={<LegalDocument />} />
      {/* Public: browsable without login, see HireProxyCounselRoute above */}
      <Route path="/hire-proxy-counsel" element={<HireProxyCounselRoute />} />

      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/order/new" element={<OrderWizard />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:orderId" element={<OrderDetail />} />
        <Route path="/marketplace" element={<Marketplace />} />
        <Route path="/courts" element={<CourtDirectory />} />
        <Route path="/ai" element={<AIAssistant />} />
        <Route path="/wallet" element={<Wallet />} />
        <Route path="/subscription" element={<Subscription />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/firm" element={<FirmManagement />} />
        <Route path="/firm/bulk-import" element={<BulkImport />} />
        <Route path="/my-data" element={<MyData />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/notifications/prefs-legacy" element={<NotificationPrefs />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/calendar" element={<Calendar />} />
        {/* Capability-gated: hidden until the account has gained a matching
            professional profile (see get_current_user's capability computation,
            server.py) — a plain advocate/customer account never sees these. */}
        <Route path="/practice" element={<ProtectedRoute capabilities={["can_practice_proxy_counsel", "can_manage_shop"]}><Practice /></ProtectedRoute>} />
        <Route path="/hearing-requests/:hearingId/negotiate" element={<ProtectedRoute capabilities={["can_hire_proxy_counsel", "can_practice_proxy_counsel"]}><NegotiationModule /></ProtectedRoute>} />
        <Route path="/hire-counsel" element={<ProtectedRoute capabilities={["can_hire_proxy_counsel"]}><HireCounsel /></ProtectedRoute>} />
        <Route path="/earnings" element={<ProtectedRoute capabilities={["can_earn"]}><Earnings /></ProtectedRoute>} />
        <Route path="/delivery" element={<ProtectedRoute roles={["delivery_partner", "admin"]}><DeliveryHub /></ProtectedRoute>} />

        <Route path="/vendor" element={<ProtectedRoute roles={["vendor", "admin"]}><VendorDashboard /></ProtectedRoute>} />
        <Route path="/vendor/onboard" element={<VendorOnboard />} />
        <Route path="/vendor/settlements" element={<ProtectedRoute roles={["vendor"]}><VendorSettlements /></ProtectedRoute>} />

        <Route path="/admin/settlements" element={<ProtectedRoute roles={["admin"]}><AdminSettlements /></ProtectedRoute>} />
        <Route path="/admin/hearing-verification" element={<ProtectedRoute roles={["admin"]}><AdminHearingVerification /></ProtectedRoute>} />

        <Route path="/admin" element={<ProtectedRoute roles={["admin"]}><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/vendors" element={<ProtectedRoute roles={["admin"]}><AdminVendors /></ProtectedRoute>} />
        <Route path="/admin/leads" element={<ProtectedRoute roles={["admin"]}><AdminLeads /></ProtectedRoute>} />
        <Route path="/admin/reviews" element={<ProtectedRoute roles={["admin"]}><AdminReviews /></ProtectedRoute>} />
        <Route path="/admin/pricing" element={<ProtectedRoute roles={["admin"]}><AdminPricing /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute roles={["admin"]}><AdminUsers /></ProtectedRoute>} />
        <Route path="/admin/reconciliation" element={<ProtectedRoute roles={["admin"]}><AdminReconciliation /></ProtectedRoute>} />
        <Route path="/admin/whatsapp" element={<ProtectedRoute roles={["admin"]}><AdminWhatsAppTemplates /></ProtectedRoute>} />
        <Route path="/admin/audit-log" element={<ProtectedRoute roles={["admin"]}><AdminAuditLog /></ProtectedRoute>} />
        <Route path="/admin/leaderboard" element={<ProtectedRoute roles={["admin"]}><AdminLeaderboard /></ProtectedRoute>} />
        <Route path="/admin/console" element={<ProtectedRoute roles={["admin"]}><SuperAdminConsole /></ProtectedRoute>} />
        <Route path="/stenographer" element={<StenographerBooking />} />
      </Route>

      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
    </Suspense>
    </>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Toaster />
          <AppRouter />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
