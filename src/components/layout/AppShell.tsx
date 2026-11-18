import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import {
  BookOpen,
  Check,
  ChevronsUpDown,
  Info,
  LayoutDashboard,
  MapPin,
  Megaphone,
  Menu,
  RotateCcw,
  ScanLine,
  Send,
  Users,
  X,
} from "lucide-react";
import { BrandLockup } from "@/components/app/Brand";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { Segmented } from "@/components/app/Segmented";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LOCATIONS } from "@/lib/demo";
import type { Role } from "@/lib/types";
import { cn, initials } from "@/lib/utils";
import { useApp } from "@/store/AppStore";

const managerNav = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/creators", label: "Creators", icon: Users },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/outreach", label: "Outreach", icon: Send },
  { to: "/briefs", label: "Weekly brief", icon: BookOpen },
];

const deskNav = [{ to: "/redeem", label: "Log a visit", icon: ScanLine }];

function LocationMenu() {
  const { location, setLocation, user } = useApp();
  const [open, setOpen] = useState(false);
  const current = LOCATIONS.find((item) => item.slug === location) ?? LOCATIONS[0];

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button className="flex w-full items-center gap-2 rounded-md border border-border/70 bg-card px-2.5 py-2 text-left transition-colors hover:border-primary/30">
          <MapPin className="size-3.5 shrink-0 text-primary" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium leading-tight text-foreground">{current.name}</span>
            <span className="block truncate text-[10px] leading-tight text-muted-foreground">{user.display_name}</span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={6}
          align="start"
          className="z-50 w-[230px] animate-scale-in rounded-lg border border-border bg-popover p-1 shadow-elegant"
        >
          <p className="px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Locations you manage
          </p>
          {LOCATIONS.map((item) => {
            const allowed = user.locations.includes(item.slug);
            return (
              <button
                key={item.slug}
                disabled={!allowed}
                onClick={() => {
                  setLocation(item.slug);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-[13px] transition-colors",
                  allowed ? "hover:bg-muted" : "cursor-not-allowed opacity-40",
                  item.slug === location ? "text-primary" : "text-foreground",
                )}
              >
                <span className="flex-1">{item.name}</span>
                {item.slug === location ? <Check className="size-3.5" /> : null}
              </button>
            );
          })}
          <p className="border-t border-border/70 px-2 py-1.5 text-[10px] leading-snug text-muted-foreground">
            Role and locations come from your profile, not the request.
          </p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  badge,
  end,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: typeof Send;
  badge?: number;
  end?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] font-medium transition-all",
          isActive
            ? "bg-sidebar-active text-foreground shadow-sm"
            : "text-sidebar-muted hover:bg-sidebar-active/60 hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon className={cn("size-4 shrink-0 transition-colors", isActive ? "text-primary" : "text-sidebar-muted group-hover:text-foreground")} />
          <span className="flex-1">{label}</span>
          {badge ? (
            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold leading-none text-primary-foreground tabular">
              {badge}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { role, setRole, summary, location, resetDemo, state } = useApp();
  const navigate = useNavigate();
  const counts = summary(location);
  const isManager = role === "manager";

  const switchRole = (next: Role) => {
    setRole(next);
    navigate(next === "manager" ? "/" : "/redeem");
    onNavigate?.();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-4 pt-5">
        <BrandLockup />
      </div>

      <div className="px-3">
        <LocationMenu />
      </div>

      <nav className="mt-4 flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {isManager ? (
          <>
            <div className="space-y-0.5">
              <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted/70">Workspace</p>
              {managerNav.map((item) => (
                <NavItem
                  key={item.to}
                  {...item}
                  badge={item.to === "/outreach" ? counts.drafts_waiting : undefined}
                  onNavigate={onNavigate}
                />
              ))}
            </div>
            <div className="space-y-0.5">
              <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted/70">Front desk</p>
              {deskNav.map((item) => (
                <NavItem key={item.to} {...item} onNavigate={onNavigate} />
              ))}
            </div>
          </>
        ) : (
          <div className="space-y-0.5">
            <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted/70">Front desk</p>
            {deskNav.map((item) => (
              <NavItem key={item.to} {...item} onNavigate={onNavigate} />
            ))}
            <p className="mx-2.5 mt-3 rounded-md bg-sidebar-active/60 p-2.5 text-[11px] leading-relaxed text-sidebar-muted">
              Managers handle creators, campaigns and drafts. Your view only logs visits.
            </p>
          </div>
        )}
      </nav>

      <div className="mt-auto space-y-3 border-t border-border/50 px-3 py-3">
        <div className="space-y-1.5">
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted/70">Viewing as</p>
          <Segmented
            size="sm"
            value={role}
            onChange={switchRole}
            options={[
              { value: "manager", label: "Manager" },
              { value: "staff", label: "Front desk" },
            ]}
          />
        </div>
        <div className="flex items-center gap-2 rounded-md px-1 py-1">
          <span className="flex size-8 items-center justify-center rounded-full bg-foreground text-[11px] font-semibold text-background">
            {initials("Tyler Wu")}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[12px] font-medium text-foreground">Tyler Wu</p>
            <p className="truncate text-[10px] text-sidebar-muted">General manager</p>
          </div>
          <button
            onClick={resetDemo}
            title={`Reset demo data (${state.campaigns.length} campaigns)`}
            aria-label="Reset demo data"
            className="rounded-sm p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-active hover:text-foreground"
          >
            <RotateCcw className="size-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { location, locationMeta } = useApp();
  const route = useLocation();

  const section = (() => {
    const path = route.pathname;
    if (path.startsWith("/creators")) return "Creators";
    if (path.startsWith("/campaigns")) return "Campaigns";
    if (path.startsWith("/outreach")) return "Outreach";
    if (path.startsWith("/briefs")) return "Weekly brief";
    if (path.startsWith("/redeem")) return "Log a visit";
    return "Overview";
  })();

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 border-r border-border/70 bg-sidebar lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
            aria-label="Close menu"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-[268px] animate-fade-in border-r border-border bg-sidebar shadow-elegant">
            <button
              className="absolute right-2 top-3 rounded-sm p-1.5 text-muted-foreground hover:bg-card"
              onClick={() => setMobileOpen(false)}
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border/70 bg-background/85 px-4 backdrop-blur-md sm:px-6">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-4" />
          </Button>
          <div className="flex min-w-0 items-center gap-2 text-[12px]">
            <MapPin className="size-3.5 text-primary" />
            <span className="truncate font-medium text-foreground">{locationMeta.name}</span>
            <span className="text-muted-foreground">/</span>
            <span className="truncate text-muted-foreground">{section}</span>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <Badge variant="outline" className="hidden gap-1.5 sm:inline-flex" title="This build renders the real API shapes with labeled sample records.">
              <Info className="size-3" />
              Sample data
            </Badge>
            <ThemeToggle />
            <div className="ml-1 flex items-center gap-2 border-l border-border/70 pl-2.5">
              <span className="hidden text-[11px] leading-tight text-muted-foreground sm:block">
                <span className="block font-medium text-foreground">Tyler Wu</span>
                <span className="block uppercase tracking-wide">{location}</span>
              </span>
              <span className="flex size-8 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">TW</span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>

        <footer className="border-t border-border/60 px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex w-full max-w-[1280px] flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-primary" />
              Feng Hotpot · creator loop
            </span>
            <span className="hidden sm:inline">Campaign dates use {locationMeta.timezone}.</span>
            <span className="ml-auto">Nothing sends automatically — a manager approves every message.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
