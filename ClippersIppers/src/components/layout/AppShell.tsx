"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAtom } from "jotai";
import {
  activeModalAtom,
  aiConfigAtom,
  projectsAtom,
  sidebarExpandedAtom,
  themeModeAtom,
} from "@/store/opusStore";
import { GlobalModals } from "./GlobalModals";
import {
  Sparkles,
  LayoutGrid,
  Palette,
  Search,
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Menu,
  X,
  Activity,
  Layers,
  Settings,
} from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarExpanded, setSidebarExpanded] = useAtom(sidebarExpandedAtom);
  const [themeMode, setThemeMode] = useAtom(themeModeAtom);
  const [projects] = useAtom(projectsAtom);
  const [aiConfig] = useAtom(aiConfigAtom);
  const [, setActiveModal] = useAtom(activeModalAtom);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Apply theme to document element
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", themeMode);
    if (themeMode === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [themeMode]);

  // Keyboard shortcut Cmd/Ctrl + K for Search
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setActiveModal("search");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setActiveModal]);

  // Active generating jobs indicator
  const activeJobs = projects.filter(
    (p) => p.stage === "RUNNING" || p.stage === "QUEUED" || p.stage === "CREATED"
  );

  const navItems = [
    {
      label: "Studio",
      href: "/dashboard",
      icon: Sparkles,
      active: pathname === "/" || pathname === "/dashboard" || pathname.startsWith("/workflow"),
    },
    {
      label: "Proyectos",
      href: "/projects",
      icon: LayoutGrid,
      active: pathname === "/projects" || pathname.startsWith("/clip/"),
    },
    {
      label: "Plantillas",
      href: "/brand-template",
      icon: Palette,
      active: pathname.startsWith("/brand-template"),
    },
  ];

  const renderSidebarContent = (isMobile = false) => {
    const expanded = isMobile ? true : sidebarExpanded;
    return (
      <div className="flex h-full flex-col justify-between select-none p-3">
        {/* Brand Header */}
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-[var(--border)]">
            <Link
              href="/dashboard"
              onClick={() => isMobile && setMobileMenuOpen(false)}
              className="flex items-center gap-2.5 overflow-hidden group"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--primary)] text-white shadow-xs group-hover:scale-105 transition">
                <Sparkles className="h-4 w-4" />
              </div>
              {expanded && (
                <div className="flex flex-col leading-tight">
                  <span className="font-bold text-sm tracking-tight text-[var(--foreground)]">
                    ClippersIppers
                  </span>
                  <span className="text-[10px] text-[var(--muted-foreground)] font-medium">
                    Local AI Video
                  </span>
                </div>
              )}
            </Link>

            {!isMobile ? (
              <button
                onClick={() => setSidebarExpanded(!sidebarExpanded)}
                className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)] transition cursor-pointer"
                title={expanded ? "Colapsar barra lateral" : "Expandir barra lateral"}
              >
                {expanded ? (
                  <ChevronLeft className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </button>
            ) : (
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="rounded-lg p-1.5 text-[var(--muted-foreground)]"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Primary Navigation */}
          <nav className="mt-4 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => isMobile && setMobileMenuOpen(false)}
                  title={!expanded ? item.label : undefined}
                  className={`flex items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold transition ${
                    item.active
                      ? "bg-[var(--primary)] text-white shadow-xs"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {expanded && <span className="truncate">{item.label}</span>}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer Utilities */}
        <div className="border-t border-[var(--border)] pt-3 space-y-1.5">
          {/* AI Connection Trigger */}
          <button
            onClick={() => {
              if (isMobile) setMobileMenuOpen(false);
              setActiveModal("ai-connect");
            }}
            title={!expanded ? "Configurar IA" : undefined}
            className={`w-full flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium border transition cursor-pointer ${
              aiConfig.isConnected
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${
                  aiConfig.isConnected ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
              {expanded && (
                <span className="truncate">
                  {aiConfig.isConnected
                    ? `IA: ${aiConfig.provider.toUpperCase()}`
                    : "Conectar IA"}
                </span>
              )}
            </div>
            {expanded && (
              <span className="text-[10px] text-[var(--muted-foreground)]">
                {aiConfig.isConnected ? "Activa" : "Configurar"}
              </span>
            )}
          </button>

          {/* Theme Switcher */}
          <button
            onClick={() => setThemeMode(themeMode === "dark" ? "light" : "dark")}
            className="w-full flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)] transition cursor-pointer"
            title={themeMode === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          >
            <div className="flex items-center gap-2">
              {themeMode === "dark" ? (
                <Sun className="h-4 w-4 text-amber-400" />
              ) : (
                <Moon className="h-4 w-4 text-slate-700" />
              )}
              {expanded && (
                <span>{themeMode === "dark" ? "Modo Claro" : "Modo Oscuro"}</span>
              )}
            </div>
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen flex bg-[var(--background)] text-[var(--foreground)]">
      {/* Desktop Sidebar (Minimalist Apple / Linear Style) */}
      <aside
        style={{ width: sidebarExpanded ? 220 : 64 }}
        className="hidden lg:block shrink-0 border-r border-[var(--border)] bg-[var(--sidebar)] transition-[width] duration-200 ease-out"
      >
        <div
          style={{ width: sidebarExpanded ? 220 : 64 }}
          className="fixed inset-y-0 left-0 z-30 border-r border-[var(--border)] bg-[var(--sidebar)] transition-[width] duration-200 ease-out"
        >
          {renderSidebarContent(false)}
        </div>
      </aside>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-50 lg:hidden bg-black/50 backdrop-blur-xs"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="h-full w-64 bg-[var(--sidebar)] border-r border-[var(--border)]"
            onClick={(e) => e.stopPropagation()}
          >
            {renderSidebarContent(true)}
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Sleek Top Navigation Bar */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--background)]/85 backdrop-blur-md px-4 sm:px-6 gap-3">
          {/* Left: Mobile Trigger & Quick Search */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden rounded-lg border border-[var(--border)] p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              aria-label="Abrir menú"
            >
              <Menu className="h-4 w-4" />
            </button>

            <button
              onClick={() => setActiveModal("search")}
              className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs text-[var(--muted-foreground)] hover:border-[var(--primary)] hover:text-[var(--foreground)] transition shadow-xs cursor-pointer"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Buscar en proyectos y transcripciones...</span>
              <span className="sm:hidden">Buscar...</span>
              <kbd className="rounded bg-[var(--secondary)] px-1.5 py-0.5 text-[10px] font-semibold border border-[var(--border)]">
                ⌘K
              </kbd>
            </button>
          </div>

          {/* Right: Generating Status Badge & AI Model Indicator */}
          <div className="flex items-center gap-2.5">
            {activeJobs.length > 0 && (
              <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--primary)]/30 bg-[var(--primary)]/10 px-2.5 py-1 text-xs font-semibold text-[var(--primary)]">
                <Activity className="h-3.5 w-3.5 animate-pulse" />
                <span>Procesando clip...</span>
              </div>
            )}

            <button
              onClick={() => setActiveModal("ai-connect")}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                aiConfig.isConnected
                  ? "border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-300 hover:bg-purple-500/15"
                  : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  aiConfig.isConnected ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
              <span className="hidden sm:inline">
                {aiConfig.isConnected
                  ? `IA: ${aiConfig.provider.toUpperCase()} (${aiConfig.model})`
                  : "Conectar IA"}
              </span>
              <span className="sm:hidden">IA</span>
            </button>
          </div>
        </header>

        {/* Viewport Content */}
        <main className="flex-1 min-w-0">{children}</main>
      </div>

      {/* Global Modals (Search, AI Connection) */}
      <GlobalModals />
    </div>
  );
}
