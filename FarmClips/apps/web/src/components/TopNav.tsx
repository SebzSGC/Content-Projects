"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Cpu, DollarSign, Film, FolderSync, Radio } from "lucide-react";
import { fetchHealth, type ServerHealth, useServerEvents } from "@/lib/api/client";

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
  }, []);

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
    }
  });

  const spent = health?.budget.spent_usd ?? 0;
  const cap = health?.budget.max_budget_usd ?? 9.0;
  const pct = Math.min(100, (spent / Math.max(0.01, cap)) * 100);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-800/80 bg-[#0A0B0F]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5">
        <div className="flex items-center gap-6">
          <Link href="/sessions" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#FFD400] text-black shadow-[0_0_18px_rgba(255,212,0,0.35)]">
              <Film className="h-4 w-4 stroke-[2.6]" />
            </span>
            <div>
              <span className="text-sm font-extrabold tracking-tight text-white">ClipsApp</span>
              <span className="ml-2 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#39FF14]">
                Híbrido v2
              </span>
            </div>
          </Link>

          <nav className="flex items-center gap-1 text-xs font-medium">
            <Link
              href="/sessions"
              className={`rounded-md px-3 py-1.5 transition ${
                pathname?.startsWith("/sessions")
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              Sesiones y Drive
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {offline ? (
            <span className="flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-500/10 px-3 py-1 text-red-300">
              <Radio className="h-3.5 w-3.5" /> Servidor desconectado (8790)
            </span>
          ) : health ? (
            <>
              <div className="hidden items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/70 px-2.5 py-1 text-zinc-300 md:flex">
                <Cpu className="h-3.5 w-3.5 text-[#39FF14]" />
                <span>
                  STT: <strong className="text-white">{health.stt_primary}</strong>
                </span>
                <span className="text-zinc-600">·</span>
                <span>
                  LLM: <strong className="text-white">{health.llm_model}</strong>
                </span>
                <span className="text-zinc-600">·</span>
                <span>{health.use_nvenc ? "NVENC" : "libx264"}</span>
              </div>

              <div className="hidden items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/70 px-2.5 py-1 text-zinc-300 lg:flex">
                <FolderSync className="h-3.5 w-3.5 text-amber-400" />
                <span>Drive: {health.drive_mode}</span>
              </div>

              <div
                className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-1"
                title={`Llamadas registradas en caché SQLite: ${health.budget.calls_count}`}
              >
                <DollarSign className="h-3.5 w-3.5 text-[#FFD400]" />
                <div className="flex flex-col">
                  <div className="flex items-center gap-1.5 font-mono text-[11px]">
                    <span className="font-semibold text-white">${spent.toFixed(4)}</span>
                    <span className="text-zinc-500">/ ${cap.toFixed(2)} USD</span>
                  </div>
                  <div className="mt-0.5 h-1 w-24 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className={`h-full transition-all ${pct > 85 ? "bg-red-500" : "bg-[#39FF14]"}`}
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}
