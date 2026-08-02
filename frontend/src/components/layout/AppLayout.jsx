import React, { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Plus, Package, Store, Building2, Sparkles, Wallet, CreditCard,
  User, Settings, LogOut, Menu, X, Scale, Bell, ChevronDown, Shield, Users, Truck,
  Receipt, MessageSquare, FileSpreadsheet, Database, Trophy, Activity, Crown, Mic, Banknote,
  UserPlus, Star, Briefcase, FileText, CalendarDays, Gavel,
} from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { formatINR } from "@/lib/api";
import { isFeatureEnabled } from "@/config/featureFlags";
import Logo from "@/components/shared/Logo";

// Workspace shell for the default (advocate / future proxy-counsel) account
// type — everything else (vendor/delivery_partner/admin below) is untouched
// legacy nav, not yet migrated to the workspace model. `{ section }` entries
// are non-clickable group headers, not links — see the render loop below.
// Grouped by user intent (Home / Services / Workspace / Finance / Account)
// rather than one flat list — same items, gates, and flags as before, just
// re-bucketed; no `to` target, capability gate, or flag was added or removed.
// "My Practice"/"Earnings" only appear once the account's capabilities
// (server.py's get_current_user) include the matching capability — a plain
// advocate account sees exactly what it saw before this nav gained sections.
const buildWorkspaceNav = (user) => {
  const capabilities = user?.capabilities || [];

  const services = [
    { to: "/order/new", icon: Plus, label: "New Order", highlight: true },
    ...(capabilities.includes("can_hire_proxy_counsel")
      ? [
          { to: "/hire-counsel", icon: Scale, label: "Hire Counsel", flag: "services.hireCounsel" },
          { to: "/hire-proxy-counsel", icon: Gavel, label: "Hire Proxy Counsel" },
        ]
      : []),
    { to: "/orders", icon: Package, label: "My Orders" },
    { to: "/marketplace", icon: Store, label: "Marketplace" },
    { to: "/stenographer", icon: Mic, label: "Stenographer" },
    { to: "/courts", icon: Building2, label: "Courts" },
    { to: "/subscription", icon: CreditCard, label: "Packages" },
  ];

  const workspace = [
    ...(capabilities.includes("can_practice_proxy_counsel") || capabilities.includes("can_manage_shop")
      ? [{ to: "/practice", icon: Briefcase, label: "My Practice" }]
      : []),
    { to: "/documents", icon: FileText, label: "Documents" },
    { to: "/calendar", icon: CalendarDays, label: "Calendar" },
    // sidebar.aiAssistant/lawFirm/bulkImport: off the founder-approved MVP
    // nav for now — routes/APIs stay registered (App.js), just not
    // discoverable from here. See config/featureFlags.js.
    { to: "/ai", icon: Sparkles, label: "AI Assistant", flag: "sidebar.aiAssistant" },
    { to: "/notifications", icon: Bell, label: "Notifications" },
    { to: "/firm", icon: Users, label: "Law Firm", flag: "sidebar.lawFirm" },
    { to: "/firm/bulk-import", icon: FileSpreadsheet, label: "Bulk Import", flag: "sidebar.bulkImport" },
  ];

  const finance = [
    { to: "/wallet", icon: Wallet, label: "Wallet" },
    ...(capabilities.includes("can_earn") ? [{ to: "/earnings", icon: Wallet, label: "Earnings" }] : []),
  ];

  const account = [
    { to: "/my-data", icon: Database, label: "My Data", flag: "sidebar.myData" },
    { to: "/profile", icon: User, label: "Profile" },
  ];

  const items = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Home" },
    { section: "Services" }, ...services,
    { section: "Workspace" }, ...workspace,
    { section: "Finance" }, ...finance,
    { section: "Account" }, ...account,
  ];
  return items.filter((item) => !item.flag || isFeatureEnabled(item.flag));
};

const navItems = (user) => {
  const role = user?.role;
  if (role === "vendor") {
    return [
      { to: "/vendor", icon: LayoutDashboard, label: "Vendor Hub" },
      { to: "/orders", icon: Package, label: "Order Queue" },
      { to: "/vendor/settlements", icon: Banknote, label: "Settlements", highlight: true },
      { to: "/wallet", icon: Wallet, label: "Earnings" },
      { to: "/notifications", icon: Bell, label: "Notifications" },
      { to: "/profile", icon: User, label: "Shop Profile" },
    ];
  }
  if (role === "delivery_partner") {
    return [
      { to: "/delivery", icon: Truck, label: "Delivery Queue", highlight: true },
      { to: "/profile", icon: User, label: "Profile" },
    ];
  }
  if (role === "admin") {
    return [
      { to: "/admin/console", icon: Crown, label: "Command Center", highlight: true },
      { to: "/admin", icon: Shield, label: "Analytics" },
      { to: "/admin/vendors", icon: Store, label: "Vendors" },
      { to: "/admin/leads", icon: UserPlus, label: "Leads" },
      { to: "/admin/reviews", icon: Star, label: "Reviews" },
      { to: "/admin/pricing", icon: CreditCard, label: "Pricing" },
      { to: "/admin/users", icon: User, label: "Users" },
      { to: "/admin/reconciliation", icon: Receipt, label: "Reconciliation" },
      { to: "/admin/settlements", icon: Banknote, label: "Settlements" },
      { to: "/admin/hearing-verification", icon: Gavel, label: "Hearing Verification" },
      { to: "/admin/whatsapp", icon: MessageSquare, label: "WhatsApp Templates" },
      { to: "/admin/leaderboard", icon: Trophy, label: "Leaderboard" },
      { to: "/admin/audit-log", icon: Activity, label: "Audit Log" },
      { to: "/orders", icon: Package, label: "All Orders" },
      { to: "/delivery", icon: Truck, label: "Delivery" },
      { to: "/courts", icon: Building2, label: "Courts" },
    ];
  }
  return buildWorkspaceNav(user);
};

export default function AppLayout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const items = navItems(user);
  const initials = (user?.name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase();

  // The sidebar's <nav> scrolls independently of the page — a route change
  // (e.g. Dashboard's "View All Notifications" link, or the topbar bell
  // button below) highlights the matching item via NavLink's own isActive,
  // but never scrolls THIS container, so an item further down the list (like
  // Notifications, well below the Services section) can end up highlighted
  // but entirely off-screen with no visual sign anything changed.
  //
  // Deliberately NOT el.scrollIntoView({block:"nearest"}) — that still
  // shifted the scroll position (and pushed items like Home out of view)
  // even when the active item was already fully visible, e.g. clicking the
  // 4th of ~5 on-screen items. Computing the two rects ourselves and only
  // touching scrollTop on the exact branch that applies guarantees a
  // genuine no-op when nothing needs to move — the sidebar's scroll
  // position is otherwise left completely alone.
  const navRefs = useRef({});
  useEffect(() => {
    const active = items.find((item) => !item.section && (
      item.to === "/dashboard" ? location.pathname === item.to : location.pathname.startsWith(item.to)
    ));
    const el = navRefs.current[active?.to];
    const container = el?.closest("nav");
    if (!el || !container) return;
    const elRect = el.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    if (elRect.top < containerRect.top) {
      container.scrollTop -= (containerRect.top - elRect.top);
    } else if (elRect.bottom > containerRect.bottom) {
      container.scrollTop += (elRect.bottom - containerRect.bottom);
    }
    // else: already fully visible — scroll position untouched, on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <aside className={`fixed lg:sticky top-0 left-0 z-40 w-72 h-screen bg-white border-r border-border transform transition-transform duration-200 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 flex flex-col`}>
        <div className="px-6 py-5 border-b border-border flex items-center justify-between">
          <Logo to="/dashboard" size="sm" data-testid="sidebar-logo" />
          <button className="lg:hidden" onClick={() => setSidebarOpen(false)} data-testid="close-sidebar-btn">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {items.map((item) => (
            item.section ? (
              <div
                key={`section-${item.section}`}
                className="px-3 pt-4 pb-1 first:pt-0 text-2xs font-bold uppercase tracking-wide text-muted-foreground/70"
              >
                {item.section}
              </div>
            ) : (
            <NavLink
              key={item.to}
              to={item.to}
              ref={(el) => { navRefs.current[item.to] = el; }}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : item.highlight
                      ? "bg-accent/10 text-accent hover:bg-accent/20"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`
              }
              end={item.to === "/dashboard"}
              onClick={() => setSidebarOpen(false)}
            >
              <item.icon className="w-[18px] h-[18px]" strokeWidth={2} />
              <span>{item.label}</span>
              {item.highlight && (
                <Badge variant="secondary" className="ml-auto bg-accent text-white border-0 text-2xs h-5 px-1.5">FAST</Badge>
              )}
            </NavLink>
            )
          ))}
        </nav>

        <div className="px-3 py-3 border-t border-border">
          <div className="rounded-xl bg-gradient-to-br from-primary to-slate-800 p-4 text-white">
            <div className="cb-overline text-white/60 mb-1">Subscription</div>
            <div className="font-display font-bold text-lg capitalize">{user?.subscription?.replace("_", " ") || "Free"}</div>
            <Link to="/subscription" className="text-xs text-accent font-semibold mt-2 inline-block" data-testid="upgrade-link">
              Upgrade plan →
            </Link>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-16 bg-white border-b border-border flex items-center justify-between px-4 sm:px-8 sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button className="lg:hidden" onClick={() => setSidebarOpen(true)} data-testid="open-sidebar-btn">
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden sm:flex items-center gap-2 text-sm">
              <span className="cb-overline">Welcome back,</span>
              <span className="font-semibold">{user?.name?.split(" ")[0] || "User"}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/wallet" className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-secondary rounded-lg" data-testid="wallet-balance-link">
              <Wallet className="w-4 h-4 text-accent" />
              <span className="text-sm font-bold">{formatINR(user?.wallet_balance || 0)}</span>
            </Link>
            <button className="relative p-2 hover:bg-secondary rounded-lg" data-testid="notifications-btn" onClick={() => navigate("/notifications")}>
              <Bell className="w-5 h-5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-accent rounded-full"></span>
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 p-1 pr-2 hover:bg-secondary rounded-lg" data-testid="user-menu-trigger">
                  <Avatar className="w-8 h-8">
                    <AvatarImage src={user?.avatar_url} />
                    <AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback>
                  </Avatar>
                  <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div className="font-bold">{user?.name}</div>
                  <div className="text-xs text-muted-foreground font-normal">{user?.email}</div>
                  <Badge variant="outline" className="mt-1.5 text-2xs capitalize">{user?.role?.replace("_", " ")}</Badge>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/profile")} data-testid="menu-profile">
                  <User className="w-4 h-4 mr-2" /> Profile
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/wallet")} data-testid="menu-wallet">
                  <Wallet className="w-4 h-4 mr-2" /> Wallet
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/subscription")} data-testid="menu-subscription">
                  <CreditCard className="w-4 h-4 mr-2" /> Subscription
                </DropdownMenuItem>
                {user?.role === "advocate" && (
                  <DropdownMenuItem onClick={() => navigate("/vendor/onboard")} data-testid="menu-become-vendor">
                    <Store className="w-4 h-4 mr-2" /> Become a Vendor
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} className="text-destructive" data-testid="menu-logout">
                  <LogOut className="w-4 h-4 mr-2" /> Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>

      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setSidebarOpen(false)}></div>
      )}
    </div>
  );
}
