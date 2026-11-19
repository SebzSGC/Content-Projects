"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  ChevronRight,
  Clapperboard,
  Cpu,
  Film,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Settings,
  Sparkles,
  Wallet,
} from "lucide-react";
import { fetchHealth, type ServerHealth, useServerEvents } from "@/lib/api/client";
import { InfoTip, StatusDot } from "@/components/ui";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isEditor = pathname?.startsWith("/editor/");
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<"dark" | "graphite">("dark");
  const [health, setHealth] = useState<ServerHealth | null>(null);
  const [offline, setOffline] = useState(false);

  // Restore user preferences from localStorage
  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem("fc_studio_theme");
      if (savedTheme === "graphite" || savedTheme === "dark") {
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
      }
      const savedCollapsed = localStorage.getItem("fc_sidenav_collapsed");
      if (savedCollapsed === "1") setCollapsed(true);
    } catch {
      // Ignore storage errors
    }
  }, []);

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setHealth(h);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, [pathname]);

  useServerEvents(undefined, (ev) => {
    if (ev.type === "budget_update" && typeof ev.spent_usd === "number") {
      setHealth((prev) =>
        prev
          ? {
              ...prev,
              budget: {
                ...prev.budget,
                spent_usd: ev.spent_usd ?? prev.budget.spent_usd,
                max_budget_usd: ev.max_budget_usd ?? prev.budget.max_budget_usd,
                remaining_usd: ev.remaining_usd ?? prev.budget.remaining_usd,
                calls_count: ev.calls_count ?? prev.budget.calls_count,
              },
            }
          : prev
      );
    } else if (ev.type === "settings_updated") {
      setHealth((prev) =>
        prev
          ? {
              ...prev,
              stt_primary: ev.stt_primary ?? prev.stt_primary,
              llm_primary: ev.llm_primary ?? prev.llm_primary,
              llm_model: ev.llm_model ?? prev.llm_model,
              budget: {
                ...prev.budget,
                max_budget_usd: ev.max_budget_usd ?? prev.budget.max_budget_usd,
              },
            }
          : prev
      );
    }
  });

  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("fc_sidenav_collapsed", next ? "1" : "0");
    } catch {
      // Ignore
    }
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "graphite" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("fc_studio_theme", next);
    } catch {
      // Ignore
    }
  };

  const spent = health?.budget.spent_usd ?? 0;
  const cap = health?.budget.max_budget_usd ?? 9.0;
  const pct = Math.min(100, (spent / Math.max(0.01, cap)) * 100);

  const isSessions = pathname === "/sessions" || pathname?.startsWith("/sessions/");
  const isAnalytics = pathname?.startsWith("/analytics");
  const isSettings = pathname?.startsWith("/settings");

  // Auto-compact sidebar when inside the 60fps Editor unless explicitly expanded
  const effectiveCollapsed = isEditor ? true : collapsed;

  const navItems = [
    {
      href: "/sessions",
      label: "Sesiones",
      sublabel: "Grabaciones y clips",
      active: Boolean(isSessions || isEditor),
      icon: Clapperboard,
    },
    {
      href: "/analytics",
      label: "Consumo y Presupuesto",
      sublabel: "Cuotas y auditoría IA",
      active: Boolean(isAnalytics),
      icon: BarChart3,
    },
    {
      href: "/settings",
      label: "Configuración",
      sublabel: "Proveedores y NLE",
      active: Boolean(isSettings),
      icon: Settings,
    },
  ];

  // Contextual breadcrumb segments
  const breadcrumbs: Array<{ label: string; href?: string }> = [{ label: "Estudio", href: "/sessions" }];
  if (pathname === "/sessions") {
    breadcrumbs.push({ label: "Sesiones de grabación" });
  } else if (pathname?.startsWith("/sessions/")) {
    breadcrumbs.push({ label: "Sesiones", href: "/sessions" });
    breadcrumbs.push({ label: "Detalle de sesión" });
  } else if (isEditor) {
    breadcrumbs.push({ label: "Sesiones", href: "/sessions" });
    breadcrumbs.push({ label: "Editor interactivo 60 fps" });
  } else if (isAnalytics) {
    breadcrumbs.push({ label: "Consumo y Presupuesto" });
  } else if (isSettings) {
    breadcrumbs.push({ label: "Configuración del sistema" });
  }

  return (
    <div className="flex min-h-screen w-full bg-[var(--color-background-body)] text-[var(--color-text-primary)]">
      {/* Desktop macOS / Astryx SideNav Rail */}
      <aside
        aria-label="Navegación principal del estudio"
        className={`hidden lg:flex lg:flex-col lg:shrink-0 border-r border-white/[0.07] bg-[var(--color-background-surface)] transition-[width] duration-200 ease-out select-none ${
          effectiveCollapsed ? "lg:w-[64px]" : "lg:w-[236px]"
        }`}
      >
        <div className="sticky top-0 flex h-screen flex-col justify-between p-2.5">
          {/* Top Brand + Rail Toggle */}
          <div className="space-y-4">
            <div
              className={`flex items-center ${
                effectiveCollapsed ? "justify-center" : "justify-between px-1.5"
              } pt-1`}
            >
              <Link href="/sessions" className="group flex items-center gap-2.5 min-w-0">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-400 text-slate-950 shadow-[0_1px_2px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.4)] transition-colors duration-150 group-hover:bg-amber-300">
                  <Film className="h-4 w-4 stroke-[2.5]" />
                </span>
                {!effectiveCollapsed && (
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-bold tracking-tight text-slate-50">
                        FarmClips
                      </span>
                      <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-amber-300">
                        Studio
                      </span>
                    </div>
                    <p className="truncate text-[10px] text-slate-500">Shorts 9:16 · IA Local</p>
                  </div>
                )}
              </Link>

              {!isEditor && !effectiveCollapsed && (
                <button
                  type="button"
                  onClick={toggleSidebar}
                  title="Contraer barra lateral"
                  className="rounded-md p-1.5 text-slate-500 transition-colors duration-150 hover:bg-white/[0.06] hover:text-slate-200 cursor-pointer"
                >
                  <PanelLeftClose className="h-4 w-4" />
                </button>
              )}
            </div>

            {!isEditor && effectiveCollapsed && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={toggleSidebar}
                  title="Expandir barra lateral"
                  className="rounded-md p-1.5 text-slate-500 transition-colors duration-150 hover:bg-white/[0.06] hover:text-slate-200 cursor-pointer"
                >
                  <PanelLeftOpen className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* Primary Navigation Links */}
            <nav className="space-y-1">
              {!effectiveCollapsed && (
                <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Espacio de trabajo
                </div>
              )}
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={effectiveCollapsed ? `${item.label} — ${item.sublabel}` : undefined}
                    className={`group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-xs font-medium transition-all duration-150 ${
                      effectiveCollapsed ? "justify-center" : ""
                    } ${
                      item.active
                        ? "bg-white/[0.07] text-slate-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                        : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
                    }`}
                  >
                    {item.active && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r bg-amber-400" />
                    )}
                    <Icon
                      className={`h-4 w-4 shrink-0 transition-colors duration-150 ${
                        item.active
                          ? "text-amber-400"
                          : "text-slate-400 group-hover:text-slate-200"
                      }`}
                    />
                    {!effectiveCollapsed && (
                      <div className="min-w-0 flex-1">
                        <span className="block truncate font-semibold leading-tight">
                          {item.label}
                        </span>
                        <span className="block truncate text-[10px] text-slate-500">
                          {item.sublabel}
                        </span>
                      </div>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Bottom Engine Telemetry & Budget Summary inside SideNav */}
          <div className="space-y-2 border-t border-white/[0.06] pt-3">
            {health && !effectiveCollapsed && (
              <div className="rounded-lg border border-white/[0.06] bg-[#0d0f15] p-2.5 text-[11px]">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="flex items-center gap-1.5 font-semibold text-slate-300">
                    <Cpu className="h-3.5 w-3.5 text-amber-400" />
                    Motor activo
                  </span>
                  <span className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                    {health.use_nvenc ? "NVENC" : "CPU"}
                  </span>
                </div>
                <div className="mt-2 space-y-1 text-[10px] text-slate-400">
                  <div className="flex items-center justify-between">
                    <span>Voz (STT)</span>
                    <span className="font-mono text-slate-200">{health.stt_primary}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="shrink-0">Curación</span>
                    <span className="truncate font-mono text-slate-200">{health.llm_model}</span>
                  </div>
                </div>
              </div>
            )}

            <Link
              href="/analytics"
              title={`Presupuesto IA: $${spent.toFixed(2)} de $${cap.toFixed(2)} USD`}
              className={`flex items-center gap-2.5 rounded-lg border border-white/[0.07] bg-white/[0.025] p-2 transition-colors duration-150 hover:border-amber-400/30 hover:bg-white/[0.05] ${
                effectiveCollapsed ? "justify-center" : ""
              }`}
            >
              <Wallet className="h-4 w-4 shrink-0 text-amber-400" />
              {!effectiveCollapsed && (
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
                    <span className="font-semibold text-slate-100">${spent.toFixed(2)}</span>
                    <span className="text-slate-500">/ ${cap.toFixed(2)}</span>
                  </div>
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className={`h-full rounded-full transition-[width] duration-500 ease-out ${
                        pct > 90 ? "bg-rose-400" : pct >= 70 ? "bg-amber-400" : "bg-emerald-400"
                      }`}
                      style={{ width: `${Math.max(3, pct)}%` }}
                    />
                  </div>
                </div>
              )}
            </Link>
          </div>
        </div>
      </aside>

      {/* Main Content Column (Sticky Contextual TopBar + Workspace Canvas) */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-white/[0.07] bg-[var(--color-background-body)]/85 backdrop-blur-md">
          <div className="mx-auto flex h-13 max-w-[1520px] items-center justify-between gap-3 px-4 sm:px-6">
            {/* Left: Mobile Brand + Contextual Breadcrumbs */}
            <div className="flex min-w-0 items-center gap-3">
              <Link href="/sessions" className="flex items-center gap-2 lg:hidden">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-400 text-slate-950">
                  <Film className="h-3.5 w-3.5 stroke-[2.5]" />
                </span>
                <span className="text-sm font-bold text-slate-50">FarmClips</span>
              </Link>

              <nav
                aria-label="Ruta actual"
                className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400 min-w-0"
              >
                {breadcrumbs.map((crumb, idx) => {
                  const isLast = idx === breadcrumbs.length - 1;
                  return (
                    <React.Fragment key={`${crumb.label}-${idx}`}>
                      {idx > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-600" />}
                      {crumb.href && !isLast ? (
                        <Link
                          href={crumb.href}
                          className="truncate font-medium text-slate-400 transition-colors duration-150 hover:text-slate-100"
                        >
                          {crumb.label}
                        </Link>
                      ) : (
                        <span className="truncate font-semibold text-slate-100">
                          {crumb.label}
                        </span>
                      )}
                    </React.Fragment>
                  );
                })}
              </nav>

              {/* Mobile Horizontal Nav Links */}
              <nav className="flex items-center gap-1 lg:hidden">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                        item.active
                          ? "bg-amber-400/15 text-amber-300"
                          : "text-slate-400 hover:bg-white/[0.05] hover:text-slate-100"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      <span className="hidden md:inline">{item.label}</span>
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* Right: Live Telemetry, Budget Pill & Studio Appearance Toggle */}
            <div className="flex items-center gap-2 text-xs">
              {offline ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 font-semibold text-rose-200">
                  <Radio className="h-3.5 w-3.5 text-rose-400" /> Servidor desconectado
                </span>
              ) : health ? (
                <>
                  <span className="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 font-medium text-slate-300 md:inline-flex">
                    <StatusDot tone="online" />
                    <span>Sistema activo</span>
                    <span className="hidden xl:inline font-mono text-[11px] text-slate-500">
                      · {health.stt_primary} / {health.llm_model}
                    </span>
                    <InfoTip label="Estado del sistema" side="bottom" align="end">
                      Todo listo para crear clips.
                      <br />
                      Voz: <span className="font-mono text-slate-100">{health.stt_primary}</span> · Selección:{" "}
                      <span className="font-mono text-slate-100">{health.llm_model}</span>
                      <br />
                      Video acelerado por {health.use_nvenc ? "tarjeta gráfica (GPU)" : "procesador"} · Estilo{" "}
                      {health.style_preset}.
                    </InfoTip>
                  </span>

                  <Link
                    href="/analytics"
                    className="flex items-center gap-2 rounded-lg border border-amber-400/25 bg-amber-400/[0.08] py-1 pl-2.5 pr-1.5 transition-colors duration-150 hover:border-amber-400/45 hover:bg-amber-400/[0.14]"
                    aria-label={`Presupuesto: ${spent.toFixed(2)} de ${cap.toFixed(2)} USD`}
                    title="Ver tu saldo y consumo detallado"
                  >
                    <Wallet className="h-3.5 w-3.5 text-amber-300" />
                    <span className="font-mono text-[11px] font-semibold tabular-nums text-amber-200">
                      ${spent.toFixed(2)}{" "}
                      <span className="font-normal text-slate-400">/ ${cap.toFixed(2)}</span>
                    </span>
                    <InfoTip label="Tu presupuesto" side="bottom" align="end">
                      Llevas ${spent.toFixed(2)} de tu límite de ${cap.toFixed(2)} USD. Si vuelves a procesar una grabación ya
                      analizada, no te cuesta nada extra gracias a la memoria local.
                    </InfoTip>
                  </Link>
                </>
              ) : null}

              <button
                type="button"
                onClick={toggleTheme}
                title={`Tema actual: ${theme === "dark" ? "Obsidiana Estudio" : "Grafito Puro"} (clic para alternar)`}
                className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] font-medium text-slate-300 transition-colors duration-150 hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-white cursor-pointer"
              >
                <Layers className="h-3.5 w-3.5 text-amber-300" />
                <span className="hidden xl:inline">
                  {theme === "dark" ? "Obsidiana" : "Grafito"}
                </span>
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}

// Keep TopNav export for backward compatibility if referenced directly
export const TopNav = AppShell;
