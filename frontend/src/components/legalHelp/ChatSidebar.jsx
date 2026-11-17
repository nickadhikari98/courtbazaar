import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ChevronDown, LogIn, PanelLeft, Plus } from "lucide-react";
import Logo from "@/components/shared/Logo";

const DAY_MS = 86400000;

/* Buckets chats (already newest first) under Today / Yesterday / Previous 7
   days / Older, by the viewer's local calendar day. Empty groups are dropped. */
export function groupChats(chats, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups = [["Today", []], ["Yesterday", []], ["Previous 7 days", []], ["Older", []]];
  for (const chat of chats) {
    const t = Date.parse(chat.updated_at) || 0;
    const idx = t >= startOfToday ? 0 : t >= startOfToday - DAY_MS ? 1 : t >= startOfToday - 7 * DAY_MS ? 2 : 3;
    groups[idx][1].push(chat);
  }
  return groups.filter(([, items]) => items.length);
}

function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

// Below the site nav (h-16 + 1px border) for guests; the whole viewport in the app layout.
// The guest drawer stays under the nav's z-40, so the nav and its menus always paint on top.
const DRAWER_AREA = { app: "inset-y-0 z-50", site: "top-[65px] bottom-0 z-30" };

export default function ChatSidebar({
  fullScreen, user, chats, activeId, onSelect, onNewChat, newChatDisabled, collapsed, onToggleCollapsed, drawerOpen, onCloseDrawer,
}) {
  // The rail (collapsed) only applies from md up; the mobile drawer is always full width.
  const rail = collapsed ? "md:w-16" : "md:w-[272px]";
  const hideOnRail = collapsed ? "md:hidden" : "";
  return (
    <>
      {drawerOpen && (
        <div className={`fixed inset-x-0 ${DRAWER_AREA[fullScreen ? "app" : "site"]} bg-black/40 md:hidden`} onClick={onCloseDrawer} aria-hidden="true"
          data-testid="chat-sidebar-overlay" />
      )}
      <aside
        className={`fixed left-0 ${DRAWER_AREA[fullScreen ? "app" : "site"]} w-[272px] ${rail} flex flex-col border-r border-border bg-slate-50 transition-[transform,width] duration-200
          md:static md:z-auto md:translate-x-0 ${drawerOpen ? "translate-x-0" : "-translate-x-full"}`}
        aria-label="Chats"
        data-testid="chat-sidebar"
      >
        <div className={`flex items-center gap-2 px-3 pt-3 pb-2 ${fullScreen ? "justify-between" : "justify-end"}`}>
          {/* Guests already see the site nav's logo: only one is ever shown. */}
          {fullScreen && <div className={hideOnRail} data-testid="chat-sidebar-logo"><Logo to="/" size="sm" /></div>}
          <button
            type="button" onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
            className="hidden md:inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-slate-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            data-testid="chat-sidebar-collapse"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        </div>

        <div className="px-3">
          <button
            type="button" onClick={onNewChat} disabled={newChatDisabled}
            aria-label="Start a new chat" title="Start a new chat"
            className="w-full inline-flex items-center justify-center gap-2 h-10 rounded-lg border border-border bg-white text-sm font-semibold hover:bg-slate-100 disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            data-testid="instant-legal-help-new-chat"
          >
            <Plus className="w-4 h-4" /><span className={hideOnRail}>New chat</span>
          </button>
        </div>

        <nav className={`flex-1 min-h-0 overflow-y-auto cb-scroll px-2 py-3 ${hideOnRail}`} data-testid="chat-sidebar-list">
          {user ? groupChats(chats).map(([label, items]) => (
            <div key={label} className="mb-3">
              <div className="px-2 pb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
              <ul>
                {items.map((c) => (
                  <li key={c.conversation_id}>
                    <button
                      type="button" onClick={() => onSelect(c.conversation_id)}
                      aria-current={c.conversation_id === activeId ? "page" : undefined}
                      className={`w-full truncate rounded-lg px-2 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        c.conversation_id === activeId ? "bg-white font-semibold shadow-sm" : "hover:bg-slate-200/60"}`}
                      title={c.title}
                    >
                      {c.title || "New chat"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )) : (
            <div className="mx-1 rounded-xl border border-border bg-white p-4 text-sm" data-testid="chat-sidebar-login">
              <p className="font-semibold">Log in to save your chats</p>
              <p className="mt-1 text-xs text-muted-foreground leading-5">Your conversations will appear here so you can pick them up later.</p>
              <Link to="/login" className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline">
                <LogIn className="w-4 h-4" />Log in
              </Link>
            </div>
          )}
        </nav>

        <div className={`border-t border-border p-3 space-y-3 ${collapsed ? "md:mt-auto" : ""}`}>
          {/* Placeholder values; wired to real usage in UI-4. */}
          <div className={`rounded-lg bg-white border border-border p-3 ${hideOnRail}`} data-testid="chat-sidebar-usage">
            <div className="flex justify-between text-xs"><span className="font-semibold">Today's questions</span><span className="text-muted-foreground">0 / 20</span></div>
            <div className="mt-2 h-1.5 rounded-full bg-slate-200"><div className="h-full w-0 rounded-full bg-accent" /></div>
          </div>
          {fullScreen && (
            <Link
              to="/" title="Back to CourtBazaar"
              className="flex items-center gap-2 rounded-lg px-1 py-1.5 text-sm text-muted-foreground hover:bg-slate-200/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="chat-sidebar-back"
            >
              <ArrowLeft className="h-4 w-4 shrink-0" /><span className={hideOnRail}>Back to CourtBazaar</span>
            </Link>
          )}
          {user && (
            <button type="button" className="w-full flex items-center gap-2 rounded-lg px-1 py-1.5 hover:bg-slate-200/60 text-sm" data-testid="chat-sidebar-user">
              <span className="h-8 w-8 shrink-0 rounded-full bg-primary text-white text-xs font-semibold flex items-center justify-center">{initials(user.name)}</span>
              <span className={`flex-1 text-left truncate ${hideOnRail}`}>{initials(user.name)} · Free</span>
              <ChevronDown className={`w-4 h-4 text-muted-foreground ${hideOnRail}`} />
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
