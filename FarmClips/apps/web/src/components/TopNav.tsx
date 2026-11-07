"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Film, Radio, Settings, Wallet } from "lucide-react";
import { fetchHealth, type ServerHealth, useServerEvents } from "@/lib/api/client";
import { InfoTip } from "@/components/ui";

export function TopNav() {
  const pathname = usePathname();
  const [health, setHealth] = useState<ServerHealth | null>(null);
  const [offline, setOffline] = useState(false);

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

  const spent = health?.budget.spent_usd ?? 0;
  const cap = health?.budget.max_budget_usd ?? 9.0;
  const pct = Math.min(100, (spent / Math.max(0.01, cap)) * 100);
  const isSettings = pathname?.startsWith("/settings");
  const isAnalytics = pathname?.startsWith("/analytics");

  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-slate-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/sessions" className="group flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-amber-400 text-slate-950 shadow-lg shadow-amber-500/25 transition-transform duration-300 group-hover:scale-105">
              <Film className="h-4 w-4 stroke-[2.6]" />
            </span>
            <span className="text-base font-black tracking-tight text-slate-50">FarmClips</span>
          </Link>

          <nav className="hidden items-center gap-1 text-sm font-bold sm:flex">
            <Link
              href="/sessions"
              className={`rounded-full px-4 py-1.5 transition-all duration-300 ${
                pathname?.startsWith("/sessions")
                  ? "bg-white/10 text-slate-50"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
              }`}
            >
              Sesiones
            </Link>
            <Link
              href="/analytics"
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 transition-all duration-300 ${
                isAnalytics
                  ? "bg-amber-400/15 text-amber-300"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              <span>Consumo y Presupuesto</span>
            </Link>
            <Link
              href="/settings"
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 transition-all duration-300 ${
                isSettings
                  ? "bg-amber-400/15 text-amber-300"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
              }`}
            >
              <Settings className="h-3.5 w-3.5" />
              <span>Configuración</span>
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-2 text-xs">
          {offline ? (
            <span className="flex items-center gap-1.5 rounded-full border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 font-bold text-rose-200">
              <Radio className="h-3.5 w-3.5" /> Servidor desconectado
            </span>
          ) : health ? (
            <>
              <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-bold text-slate-300 md:inline-flex">
                <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
                Servidor listo
                <InfoTip label="Detalles del servidor" side="bottom" align="end">
                  STT: <span className="font-mono text-slate-100">{health.stt_primary}</span> (respaldo{" "}
                  {health.stt_backup})
                  <br />
                  LLM: <span className="font-mono text-slate-100">{health.llm_model}</span> (respaldo{" "}
                  {health.llm_backup})
                  <br />
                  Render: {health.use_nvenc ? "NVENC" : "libx264"} · {health.render_slots} slots ·{" "}
                  {health.cpu_workers} núcleos
                  <br />
                  Drive: {health.drive_mode} · Preset: {health.style_preset}
                </InfoTip>
              </span>

              <Link
                href="/analytics"
                className="flex items-center gap-2.5 rounded-full border border-amber-300/25 bg-amber-400/10 py-1.5 pl-3 pr-2 transition-colors hover:border-amber-300/45 hover:bg-amber-400/15"
                aria-label={`Presupuesto: ${spent.toFixed(2)} de ${cap.toFixed(2)} USD`}
                title="Abrir panel de Consumo y Presupuesto (/analytics)"
              >
                <Wallet className="h-3.5 w-3.5 text-amber-300" />
                <span className="flex flex-col">
                  <span className="font-mono text-[11px] font-bold leading-none text-amber-200">
                    ${spent.toFixed(2)} <span className="font-normal text-slate-400">/ ${cap.toFixed(2)}</span>
                  </span>
                  <span className="mt-1 h-1 w-20 overflow-hidden rounded-full bg-white/10">
                    <span
                      className={`block h-full rounded-full transition-[width] duration-700 ease-out ${
                        pct > 90 ? "bg-rose-400" : pct >= 70 ? "bg-amber-400" : "bg-emerald-400"
                      }`}
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </span>
                </span>
                <InfoTip label="Detalle del presupuesto" side="bottom" align="end">
                  Gastado ${spent.toFixed(4)} de ${cap.toFixed(2)} USD. {health.budget.calls_count} llamadas guardadas
                  en caché: repetir una sesión no vuelve a cobrar.
                </InfoTip>
              </Link>
            </>
          ) : null}

          <Link
            href="/analytics"
            title="Analíticas de Consumo y Presupuesto"
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-bold transition-all duration-300 sm:hidden ${
              isAnalytics
                ? "border-amber-300/40 bg-amber-400/15 text-amber-300"
                : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:bg-white/10 hover:text-slate-50"
            }`}
          >
            <BarChart3 className="h-3.5 w-3.5" />
          </Link>

          <Link
            href="/settings"
            title="Configuración de API Keys y Proveedores"
            className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 font-bold transition-all duration-300 ${
              isSettings
                ? "border-amber-300/40 bg-amber-400/15 text-amber-300"
                : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:bg-white/10 hover:text-slate-50"
            }`}
          >
            <Settings className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Ajustes</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
