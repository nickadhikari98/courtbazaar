import React, { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { setToken } from "@/lib/api";

import Landing from "@/pages/marketing/Landing";
import Pricing from "@/pages/marketing/Pricing";
import VendorOnboarding from "@/pages/marketing/VendorOnboarding";
import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import Dashboard from "@/pages/customer/Dashboard";
import OrderWizard from "@/pages/customer/OrderWizard";
import OrderDetail from "@/pages/customer/OrderDetail";
import Orders from "@/pages/customer/Orders";
import Marketplace from "@/pages/customer/Marketplace";
import CourtDirectory from "@/pages/customer/CourtDirectory";
import AIAssistant from "@/pages/customer/AIAssistant";
import Wallet from "@/pages/customer/Wallet";
import Subscription from "@/pages/customer/Subscription";
import Profile from "@/pages/customer/Profile";
import BulkImport from "@/pages/customer/BulkImport";
import MyData from "@/pages/customer/MyData";
import FirmManagement from "@/pages/customer/FirmManagement";
import NotificationPrefs from "@/pages/customer/NotificationPrefs";
import VendorDashboard from "@/pages/vendor/VendorDashboard";
import VendorOnboard from "@/pages/vendor/VendorOnboard";
import VendorSettlements from "@/pages/vendor/VendorSettlements";
import AdminSettlements from "@/pages/admin/AdminSettlements";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import AdminVendors from "@/pages/admin/AdminVendors";
import AdminLeads from "@/pages/admin/AdminLeads";
import AdminPricing from "@/pages/admin/AdminPricing";
import AdminUsers from "@/pages/admin/AdminUsers";
import AdminReconciliation from "@/pages/admin/AdminReconciliation";
import AdminWhatsAppTemplates from "@/pages/admin/AdminWhatsAppTemplates";
import AdminAuditLog from "@/pages/admin/AdminAuditLog";
import AdminLeaderboard from "@/pages/admin/AdminLeaderboard";
import SuperAdminConsole from "@/pages/admin/SuperAdminConsole";
import DeliveryHub from "@/pages/delivery/DeliveryHub";
import StenographerBooking from "@/pages/special/StenographerBooking";
import AppLayout from "@/components/layout/AppLayout";

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

function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
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
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/vendor-signup" element={<VendorOnboarding />} />

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
        <Route path="/notifications" element={<NotificationPrefs />} />
        <Route path="/delivery" element={<ProtectedRoute roles={["delivery_partner", "admin"]}><DeliveryHub /></ProtectedRoute>} />

        <Route path="/vendor" element={<ProtectedRoute roles={["vendor", "admin"]}><VendorDashboard /></ProtectedRoute>} />
        <Route path="/vendor/onboard" element={<VendorOnboard />} />
        <Route path="/vendor/settlements" element={<ProtectedRoute roles={["vendor"]}><VendorSettlements /></ProtectedRoute>} />

        <Route path="/admin/settlements" element={<ProtectedRoute roles={["admin"]}><AdminSettlements /></ProtectedRoute>} />

        <Route path="/admin" element={<ProtectedRoute roles={["admin"]}><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/vendors" element={<ProtectedRoute roles={["admin"]}><AdminVendors /></ProtectedRoute>} />
        <Route path="/admin/leads" element={<ProtectedRoute roles={["admin"]}><AdminLeads /></ProtectedRoute>} />
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
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Toaster position="top-right" richColors />
          <AppRouter />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
