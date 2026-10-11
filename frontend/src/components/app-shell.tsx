"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import {
  Bell,
  BookOpen,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileVideo,
  Home,
  Menu,
  MessageSquareText,
  Moon,
  Search,
  Send,
  Settings,
  Sun,
  Upload,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useTheme } from "@/hooks/use-theme";

type NavItem = { href: string; label: string; icon: typeof Home };

const mainNavigation: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/library", label: "My Library", icon: FileVideo },
  { href: "/history", label: "Chat History", icon: Clock3 },
  { href: "/uploads", label: "Uploads", icon: Upload },
  { href: "/settings", label: "Settings", icon: Settings },
];

const quickNavigation: NavItem[] = [
  { href: "/help#how-it-works", label: "How it works", icon: CircleHelp },
  { href: "/help", label: "Help & Docs", icon: BookOpen },
  { href: "mailto:feedback@videoqa.local", label: "Feedback", icon: Send },
];

function Brand() {
  return (
    <Link href="/" className="brand" aria-label="VideoQA home">
      <span className="brand-mark" aria-hidden="true"><span /></span>
      <span>Video<span>QA</span></span>
    </Link>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const isActive = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <nav className="side-navigation" aria-label="Primary navigation">
      <div className="nav-group">
        {mainNavigation.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} onClick={onNavigate} className={`nav-link ${isActive(href) ? "active" : ""}`}>
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ))}
      </div>
      <div className="nav-divider" />
      <p className="nav-label">Quick links</p>
      <div className="nav-group nav-group-secondary">
        {quickNavigation.map(({ href, label, icon: Icon }) => (
          <Link key={label} href={href} onClick={onNavigate} className="nav-link">
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="sidebar-top"><Brand /></div>
      <Navigation onNavigate={onNavigate} />
      <div className="account-card">
        <span className="avatar avatar-blue" aria-hidden="true">V</span>
        <span className="account-copy"><strong>Vedant</strong><small>Local workspace</small></span>
        <ChevronRight size={16} aria-hidden="true" />
      </div>
    </>
  );
}

function TopBar({ openMenu }: { openMenu: () => void }) {
  const router = useRouter();
  const { preference, setPreference, mounted } = useTheme();
  const [search, setSearch] = useState("");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    api.health().then((health) => {
      if (active) setOnline(Boolean(health.services?.api === "ok" || health.status === "ok" || health.status === "degraded"));
    }).catch(() => {
      if (active) setOnline(false);
    });
    return () => { active = false; };
  }, []);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const query = search.trim();
    router.push(query ? `/library?q=${encodeURIComponent(query)}` : "/library");
  };

  const dark = mounted && preference === "dark" || (!mounted && false);
  return (
    <header className="topbar">
      <button type="button" className="icon-button mobile-menu" onClick={openMenu} aria-label="Open navigation">
        <Menu size={20} />
      </button>
      <form className="global-search" onSubmit={submitSearch} role="search">
        <Search size={18} aria-hidden="true" />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search your library" aria-label="Search your library" />
        <kbd>⌘ K</kbd>
      </form>
      <div className="topbar-actions">
        <span className={`connection-status ${online === false ? "offline" : ""}`} title={online === false ? "Backend unavailable" : "Backend connected"}>
          <span /> <span className="connection-copy">{online === false ? "Offline" : "Connected"}</span>
        </span>
        <button type="button" className="icon-button" aria-label={dark ? "Use light theme" : "Use dark theme"} onClick={() => setPreference(dark ? "light" : "dark")}>
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button type="button" className="icon-button notifications" aria-label="Notifications"><Bell size={18} /></button>
        <span className="avatar avatar-neutral" title="Vedant">V</span>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="app-frame">
      <aside className="sidebar"><Sidebar /></aside>
      <div className="mobile-top-brand"><Brand /></div>
      {menuOpen && <button type="button" className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`mobile-sidebar ${menuOpen ? "is-open" : ""}`} aria-hidden={!menuOpen}>
        <button type="button" className="icon-button sidebar-close" aria-label="Close navigation" onClick={() => setMenuOpen(false)}><X size={20} /></button>
        <Sidebar onNavigate={() => setMenuOpen(false)} />
      </aside>
      <div className="app-main">
        <TopBar openMenu={() => setMenuOpen(true)} />
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
