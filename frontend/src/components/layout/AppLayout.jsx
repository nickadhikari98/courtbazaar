import React, { useState } from "react";
import { NavLink, Outlet, Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Plus, Package, Store, Building2, Sparkles, Wallet, CreditCard,
  User, Settings, LogOut, Menu, X, Scale, Bell, ChevronDown, Shield, Users, Truck,
  Receipt, MessageSquare, FileSpreadsheet, Database, Trophy, Activity, Crown, Mic, Banknote,
  UserPlus,
} from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { formatINR } from "@/lib/api";

const navItems = (role) => {
  const common = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/order/new", icon: Plus, label: "New Order", highlight: true },
    { to: "/orders", icon: Package, label: "My Orders" },
    { to: "/marketplace", icon: Store, label: "Marketplace" },
    { to: "/stenographer", icon: Mic, label: "Stenographer" },
    { to: "/courts", icon: Building2, label: "Courts" },
    { to: "/ai", icon: Sparkles, label: "AI Assistant" },
    { to: "/firm", icon: Users, label: "Law Firm" },
    { to: "/firm/bulk-import", icon: FileSpreadsheet, label: "Bulk Import" },
    { to: "/wallet", icon: Wallet, label: "Wallet" },
    { to: "/my-data", icon: Database, label: "My Data" },
    { to: "/notifications", icon: Bell, label: "Notifications" },
    { to: "/subscription", icon: CreditCard, label: "Plans" },
  ];
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
      { to: "/admin/pricing", icon: CreditCard, label: "Pricing" },
      { to: "/admin/users", icon: User, label: "Users" },
      { to: "/admin/reconciliation", icon: Receipt, label: "Reconciliation" },
      { to: "/admin/settlements", icon: Banknote, label: "Settlements" },
      { to: "/admin/whatsapp", icon: MessageSquare, label: "WhatsApp Templates" },
      { to: "/admin/leaderboard", icon: Trophy, label: "Leaderboard" },
      { to: "/admin/audit-log", icon: Activity, label: "Audit Log" },
      { to: "/orders", icon: Package, label: "All Orders" },
      { to: "/delivery", icon: Truck, label: "Delivery" },
      { to: "/courts", icon: Building2, label: "Courts" },
    ];
  }
  return common;
};

export default function AppLayout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const items = navItems(user?.role);
  const initials = (user?.name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-40 w-72 bg-white border-r border-border transform transition-transform duration-200 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 flex flex-col`}>
        <div className="px-6 py-5 border-b border-border flex items-center justify-between">
          <Link to="/dashboard" className="flex items-center gap-2.5" data-testid="sidebar-logo">
            <div className="w-9 h-9 bg-primary rounded-lg flex items-center justify-center">
              <Scale className="w-5 h-5 text-white" strokeWidth={2} />
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-display font-black text-lg tracking-tight">CourtBazaar</span>
              <span className="text-2xs uppercase tracking-[0.18em] text-muted-foreground font-bold">India</span>
            </div>
          </Link>
          <button className="lg:hidden" onClick={() => setSidebarOpen(false)} data-testid="close-sidebar-btn">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
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
            <button className="relative p-2 hover:bg-secondary rounded-lg" data-testid="notifications-btn">
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
