"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  Calculator,
  Calendar,
  CheckCircle2,
  Clock,
  Cpu,
  DollarSign,
  Filter,
  Headphones,
  Layers,
  Mic,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import {
  fetchAnalyticsBreakdown,
  fetchAnalyticsLogs,
  fetchAnalyticsSummary,
  type AnalyticsAlertStatus,
  type AnalyticsBreakdown,
  type AnalyticsFreeTierModel,
  type AnalyticsLogsResponse,
  type AnalyticsSummary,
  useServerEvents,
} from "@/lib/api/client";

function formatCompactMetric(val: number): string {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(2).replace(/\.00$/, "")}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(2).replace(/\.00$/, "")}K`;
  return Number.isInteger(val) ? String(val) : val.toFixed(1);
}

function AiStudioProgressCell({
  used,
  limit,
  formatValue,
}: {
  used: number;
  limit: number;
  formatValue?: (v: number) => string;
}) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const fmt = formatValue ?? ((v: number) => String(v));
  const isHigh = pct >= 85;
  const isMid = pct >= 50 && pct < 85;
  const dotColor = isHigh ? "bg-rose-400 ring-rose-400/40" : isMid ? "bg-amber-400 ring-amber-400/40" : "bg-slate-100 ring-white/30";
  const fillColor = isHigh ? "bg-rose-400/80" : isMid ? "bg-amber-400/80" : "bg-emerald-400/80";

  return (
    <div className="flex items-center gap-3">
      <div className="relative h-1.5 w-24 rounded-full bg-white/10">
        <div className={`h-full rounded-full transition-all duration-500 ${fillColor}`} style={{ width: `${pct}%` }} />
        <span
          className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 transition-all duration-500 ${dotColor}`}
          style={{ left: `${Math.max(3, Math.min(97, pct))}%` }}
        />
      </div>
      <span className="whitespace-nowrap font-mono text-xs font-bold text-slate-200">
        {fmt(used)} <span className="font-normal text-slate-400">/ {fmt(limit)}</span>
      </span>
    </div>
  );
}

function AiStudioPeakChartCard({
  title,
  limit,
  peakValue,
  series,
  formatAxis,
}: {
  title: string;
  limit: number;
  peakValue: number;
  series: { label: string; value: number }[];
  formatAxis: (v: number) => string;
}) {
  const width = 320;
  const height = 140;
  const padLeft = 12;
  const padRight = 38;
  const padTop = 22;
  const padBottom = 26;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const yMax = Math.max(limit * 1.15, peakValue * 1.15, 1);
  const yFor = (val: number) => padTop + plotH - Math.min(1, Math.max(0, val / yMax)) * plotH;
  const limitY = yFor(limit);
  const baselineY = yFor(0);

  const pts = series.length > 0 ? series : [{ label: "00:00", value: 0 }, { label: "Ahora", value: peakValue }];
  const coords = pts.map((p, idx) => {
    const x = padLeft + (idx / Math.max(1, pts.length - 1)) * plotW;
    const y = yFor(p.value);
    return { x, y, label: p.label, value: p.value };
  });

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${coords[coords.length - 1].x.toFixed(1)},${baselineY.toFixed(1)} L${coords[0].x.toFixed(1)},${baselineY.toFixed(1)} Z`;
  const lastPt = coords[coords.length - 1];
  const pctOfLimit = limit > 0 ? ((peakValue / limit) * 100).toFixed(1) : "0.0";

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/75 p-4 shadow-inner">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-slate-200">{title}</span>
        <span className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-[11px] font-bold text-emerald-300">
          Pico: {formatAxis(peakValue)} ({pctOfLimit}%)
        </span>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="h-36 w-full overflow-visible">
        {/* Horizontal grid lines */}
        {[0, 0.5, 1].map((step) => {
          const val = limit * step;
          const y = yFor(val);
          return (
            <g key={step}>
              <line
                x1={padLeft}
                y1={y}
                x2={padLeft + plotW}
                y2={y}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth="1"
              />
              <text
                x={padLeft + plotW + 6}
                y={y + 3}
                fill="rgba(148,163,184,0.85)"
                fontSize="9"
                fontFamily="monospace"
              >
                {formatAxis(val)}
              </text>
            </g>
          );
        })}

        {/* Red dashed Free-Tier Limit line + "Limit" pill (AI Studio style) */}
        <line
          x1={padLeft}
          y1={limitY}
          x2={padLeft + plotW}
          y2={limitY}
          stroke="#f43f5e"
          strokeWidth="1.5"
          strokeDasharray="3 3"
        />
        <rect x={padLeft} y={limitY - 8} width="28" height="13" rx="3" fill="#e11d48" />
        <text x={padLeft + 14} y={limitY + 1} textAnchor="middle" fill="#ffffff" fontSize="8" fontWeight="bold">
          Limit
        </text>

        {/* Area under usage curve */}
        <path d={areaPath} fill="rgba(56, 189, 248, 0.18)" />
        {/* Usage curve */}
        <path d={linePath} fill="none" stroke="#e2e8f0" strokeWidth="1.6" strokeLinejoin="round" />

        {/* End dot */}
        {lastPt && (
          <circle
            cx={lastPt.x}
            cy={lastPt.y}
            r="3"
            fill="#38bdf8"
            stroke="#0f172a"
            strokeWidth="1.5"
          />
        )}

        {/* X axis labels */}
        <text x={padLeft} y={height - 6} fill="rgba(148,163,184,0.8)" fontSize="9" fontFamily="monospace">
          -24h ({coords[0]?.label})
        </text>
        <text
          x={padLeft + plotW / 2}
          y={height - 6}
          textAnchor="middle"
          fill="rgba(148,163,184,0.7)"
          fontSize="9"
          fontFamily="monospace"
        >
          {coords[Math.floor(coords.length / 2)]?.label}
        </text>
        <text
          x={padLeft + plotW}
          y={height - 6}
          textAnchor="end"
          fill="rgba(226,232,240,0.9)"
          fontSize="9"
          fontFamily="monospace"
        >
          Hoy ({lastPt?.label})
        </text>
      </svg>
    </div>
  );
}

const PROVIDER_META: Record<
  string,
  { label: string; colorBar: string; badgeBg: string; badgeText: string; border: string }
> = {
  deepgram: {
    label: "Deepgram",
    colorBar: "from-emerald-400 to-teal-500",
    badgeBg: "bg-emerald-500/15",
    badgeText: "text-emerald-300",
    border: "border-emerald-400/30",
  },
  gemini: {
    label: "Google Gemini",
    colorBar: "from-sky-400 to-indigo-500",
    badgeBg: "bg-sky-500/15",
    badgeText: "text-sky-300",
    border: "border-sky-400/30",
  },
  groq: {
    label: "Groq Cloud",
    colorBar: "from-amber-400 to-orange-500",
    badgeBg: "bg-amber-500/15",
    badgeText: "text-amber-300",
    border: "border-amber-400/30",
  },
  openai: {
    label: "OpenAI",
    colorBar: "from-violet-400 to-fuchsia-500",
    badgeBg: "bg-violet-500/15",
    badgeText: "text-violet-300",
    border: "border-violet-400/30",
  },
  openai_compat: {
    label: "OpenAI Compat",
    colorBar: "from-violet-400 to-fuchsia-500",
    badgeBg: "bg-violet-500/15",
    badgeText: "text-violet-300",
    border: "border-violet-400/30",
  },
};

function getProviderMeta(provider: string) {
  const key = (provider || "").toLowerCase();
  return (
    PROVIDER_META[key] ?? {
      label: provider || "Proveedor",
      colorBar: "from-slate-400 to-slate-500",
      badgeBg: "bg-white/10",
      badgeText: "text-slate-200",
      border: "border-white/20",
    }
  );
}

function getAlertMeta(status: AnalyticsAlertStatus) {
  switch (status) {
    case "BLOCKED":
      return {
        label: "BLOQUEADO (TOPE ALCANZADO)",
        barClass: "from-rose-500 via-red-500 to-rose-600",
        badgeClass: "border-rose-400/40 bg-rose-500/20 text-rose-200",
        panelClass: "border-rose-500/35 bg-rose-950/30",
        icon: ShieldAlert,
        description:
          "El gasto alcanzó el 100% del presupuesto máximo. Las nuevas llamadas a APIs están bloqueadas hasta ampliar el tope en Configuración.",
      };
    case "CRITICAL":
      return {
        label: "CRÍTICO (> 90%)",
        barClass: "from-rose-500 via-amber-500 to-red-500",
        badgeClass: "border-rose-400/40 bg-rose-500/15 text-rose-200",
        panelClass: "border-rose-500/30 bg-rose-950/20",
        icon: AlertTriangle,
        description:
          "Atención: has superado el 90% de tu presupuesto configurado. Revisa el saldo antes de lanzar grabaciones largas.",
      };
    case "WARNING":
      return {
        label: "ADVERTENCIA (70% - 90%)",
        barClass: "from-amber-400 via-amber-500 to-orange-500",
        badgeClass: "border-amber-400/40 bg-amber-500/15 text-amber-200",
        panelClass: "border-amber-500/25 bg-amber-950/20",
        icon: AlertTriangle,
        description:
          "Consumo moderado-alto (entre 70% y 90% del límite). Los artefactos ya procesados siguen en caché a $0.00.",
      };
    default:
      return {
        label: "NORMAL (< 70%)",
        barClass: "from-emerald-400 via-teal-400 to-cyan-400",
        badgeClass: "border-emerald-400/30 bg-emerald-500/15 text-emerald-300",
        panelClass: "border-emerald-500/20 bg-emerald-950/15",
        icon: CheckCircle2,
        description:
          "Presupuesto saludable. El candado de presupuesto y la caché por hash están activos para evitar cobros duplicados.",
      };
  }
}

function formatDateTime(ts: number, isoFallback?: string): string {
  if (!ts && !isoFallback) return "—";
  try {
    const d = ts ? new Date(ts * 1000) : new Date(isoFallback!);
    return d.toLocaleString("es-CO", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoFallback || "—";
  }
}

export default function AnalyticsDashboardPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [breakdown, setBreakdown] = useState<AnalyticsBreakdown | null>(null);
  const [logsData, setLogsData] = useState<AnalyticsLogsResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Filters for audit logs
  const [filterProvider, setFilterProvider] = useState<string>("all");
  const [filterKind, setFilterKind] = useState<string>("all");
  const [filterSession, setFilterSession] = useState<string>("all");
  const [filterDateFrom, setFilterDateFrom] = useState<string>("");
  const [filterDateTo, setFilterDateTo] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [pageOffset, setPageOffset] = useState<number>(0);
  const pageLimit = 25;

  // Interactive Cost Simulator state
  const [simHours, setSimHours] = useState<number>(2.0);
  const [simProfile, setSimProfile] = useState<"empirical" | "deepgram_gemini" | "groq_gemini">("empirical");
  const [selectedFreeTierModelId, setSelectedFreeTierModelId] = useState<string>("gemini-3.5-flash-lite");

  const loadAnalytics = useCallback(
    async (isManualRefresh = false) => {
      if (isManualRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      try {
        const [sumRes, brkRes, logsRes] = await Promise.all([
          fetchAnalyticsSummary(),
          fetchAnalyticsBreakdown(),
          fetchAnalyticsLogs({
            provider: filterProvider,
            kind: filterKind,
            session_id: filterSession,
            date_from: filterDateFrom || undefined,
            date_to: filterDateTo || undefined,
            search: searchQuery.trim() || undefined,
            limit: pageLimit,
            offset: pageOffset,
          }),
        ]);
        setSummary(sumRes);
        setBreakdown(brkRes);
        setLogsData(logsRes);
        setLastUpdated(new Date());
      } catch (err) {
        setError(err instanceof Error ? err.message : "No se pudieron cargar las analíticas de consumo.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [filterProvider, filterKind, filterSession, filterDateFrom, filterDateTo, searchQuery, pageOffset]
  );

  useEffect(() => {
    loadAnalytics(false);
  }, [loadAnalytics]);

  // Live refresh when server emits budget_update SSE
  useServerEvents(undefined, (ev) => {
    if (ev.type === "budget_update" || ev.type === "settings_updated") {
      loadAnalytics(true);
    }
  });

  // Reset pagination when filters change
  const handleFilterChange = <T,>(setter: React.Dispatch<React.SetStateAction<T>>, val: T) => {
    setPageOffset(0);
    setter(val);
  };

  // Simulator calculations
  const simResult = useMemo(() => {
    const hours = Math.max(0.1, Number.isFinite(simHours) ? simHours : 1.0);
    const proj = summary?.projections;

    let sttRatePerHour = proj?.stt_cost_per_stream_hour_usd ?? 0.258;
    let llmRatePerHour = proj?.llm_cost_per_stream_hour_usd ?? 0.0094;
    let clipsPerHour = proj?.avg_clips_per_stream_hour ?? 3.0;
    let tokensPerHour = proj?.avg_tokens_per_stream_hour ?? 25200;

    if (simProfile === "deepgram_gemini") {
      sttRatePerHour = 0.0043 * 60; // $0.2580/h
      llmRatePerHour = 0.0094;
    } else if (simProfile === "groq_gemini") {
      sttRatePerHour = 0.00067 * 60; // $0.0402/h
      llmRatePerHour = 0.0094;
    }

    const sttCost = hours * sttRatePerHour;
    const llmCost = hours * llmRatePerHour;
    const totalCost = sttCost + llmCost;
    const estClips = Math.max(1, Math.round(hours * clipsPerHour));
    const estTokens = Math.round(hours * tokensPerHour);
    const estChunks = Math.ceil((hours * 3600) / 600);
    const remaining = summary?.remaining_usd ?? 9.0;
    const fitsBudget = totalCost <= remaining;
    const remainingAfter = Math.max(0, remaining - totalCost);

    return {
      hours,
      sttRatePerHour,
      llmRatePerHour,
      sttCost,
      llmCost,
      totalCost,
      estClips,
      estTokens,
      estChunks,
      fitsBudget,
      remainingAfter,
    };
  }, [simHours, simProfile, summary]);

  // Unified provider comparison rows (ensuring Deepgram, Gemini, Groq, OpenAI are visible for comparison)
  const providerComparison = useMemo(() => {
    const existing = breakdown?.by_provider ?? [];
    const spentTotal = Math.max(0.000001, summary?.spent_usd ?? 0);
    const map = new Map<
      string,
      {
        provider: string;
        calls: number;
        cost_usd: number;
        share_pct: number;
        audio_minutes: number;
        total_tokens: number;
        avg_latency_ms: number;
        kinds: string[];
      }
    >();

    for (const item of existing) {
      const k = item.provider.toLowerCase();
      const prev = map.get(k);
      if (prev) {
        prev.calls += item.calls;
        prev.cost_usd += item.cost_usd;
        prev.audio_minutes += item.audio_minutes;
        prev.total_tokens += item.total_tokens;
        prev.avg_latency_ms = Math.round((prev.avg_latency_ms + item.avg_latency_ms) / 2);
        if (!prev.kinds.includes(item.kind)) prev.kinds.push(item.kind);
      } else {
        map.set(k, {
          provider: k,
          calls: item.calls,
          cost_usd: item.cost_usd,
          share_pct: item.share_pct,
          audio_minutes: item.audio_minutes,
          total_tokens: item.total_tokens,
          avg_latency_ms: item.avg_latency_ms,
          kinds: [item.kind],
        });
      }
    }

    for (const baseProv of [
      { id: "deepgram", defaultKind: "stt" },
      { id: "gemini", defaultKind: "llm" },
      { id: "groq", defaultKind: "stt" },
      { id: "openai", defaultKind: "llm" },
    ]) {
      if (!map.has(baseProv.id)) {
        map.set(baseProv.id, {
          provider: baseProv.id,
          calls: 0,
          cost_usd: 0,
          share_pct: 0,
          audio_minutes: 0,
          total_tokens: 0,
          avg_latency_ms: 0,
          kinds: [baseProv.defaultKind],
        });
      }
    }

    return Array.from(map.values())
      .map((item) => ({
        ...item,
        share_pct: summary && summary.spent_usd > 0 ? Number(((item.cost_usd / spentTotal) * 100).toFixed(2)) : 0,
      }))
      .sort((a, b) => b.cost_usd - a.cost_usd || b.calls - a.calls);
  }, [breakdown, summary]);

  const alertMeta = getAlertMeta(summary?.alert_status ?? "NORMAL");
  const AlertIcon = alertMeta.icon;
  const usagePct = Math.min(100, summary?.usage_pct ?? 0);
  const inputTokPct =
    summary && summary.total_tokens > 0 ? Math.round((summary.input_tokens / summary.total_tokens) * 1000) / 10 : 0;
  const outputTokPct = summary && summary.total_tokens > 0 ? Math.round((100 - inputTokPct) * 10) / 10 : 0;

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <Link
            href="/sessions"
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-bold text-slate-400 transition-colors hover:text-slate-200"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Volver a Sesiones
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="flex items-center gap-3 text-2xl font-black tracking-tight text-slate-50 sm:text-3xl">
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-400/15 text-amber-300 ring-1 ring-amber-300/30">
                <BarChart3 className="h-5 w-5" />
              </span>
              Analíticas y Trazabilidad de APIs
            </h1>
            {summary && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-extrabold ${alertMeta.badgeClass}`}
              >
                <AlertIcon className="h-3.5 w-3.5" />
                {alertMeta.label}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Auditoría en tiempo real de llamadas a Deepgram, Gemini, Groq y OpenAI, proyecciones de capacidad y simulador de costos.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {lastUpdated && (
            <span className="text-xs text-slate-500">
              Actualizado:{" "}
              <span className="font-mono text-slate-300">
                {lastUpdated.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
            </span>
          )}
          <button
            type="button"
            onClick={() => loadAnalytics(true)}
            disabled={refreshing || loading}
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs font-bold text-slate-100 transition-all hover:border-amber-300/40 hover:bg-amber-400/15 hover:text-amber-200 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-amber-300" : ""}`} />
            {refreshing ? "Actualizando..." : "Refrescar en tiempo real"}
          </button>
          <Link
            href="/settings"
            className="inline-flex items-center gap-1.5 rounded-full bg-amber-400 px-4 py-2 text-xs font-black text-slate-950 shadow-lg shadow-amber-500/20 transition-all hover:bg-amber-300"
          >
            <Wallet className="h-3.5 w-3.5" />
            Ajustar Tope USD
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          <AlertTriangle className="h-5 w-5 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* 1. KPI Cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: Gasto Total USD */}
        <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-900/75 p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Gasto Acumulado</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-400/15 text-amber-300">
              <DollarSign className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-50">
              ${(summary?.spent_usd ?? 0).toFixed(4)}
            </span>
            <span className="text-xs font-bold text-slate-400">USD</span>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5 text-xs text-slate-400">
            <span>
              STT: <strong className="font-mono text-emerald-300">${(summary?.stt_cost_usd ?? 0).toFixed(4)}</strong>
            </span>
            <span>
              LLM: <strong className="font-mono text-sky-300">${(summary?.llm_cost_usd ?? 0).toFixed(4)}</strong>
            </span>
          </div>
        </div>

        {/* Card 2: Saldo Restante */}
        <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-900/75 p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Saldo Restante</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-400/15 text-emerald-300">
              <Wallet className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-emerald-300">
              ${(summary?.remaining_usd ?? 0).toFixed(4)}
            </span>
            <span className="text-xs font-bold text-slate-400">
              / ${(summary?.max_budget_usd ?? 9.0).toFixed(2)}
            </span>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5 text-xs text-slate-400">
            <span>
              Consumo: <strong className="font-mono text-slate-200">{(summary?.usage_pct ?? 0).toFixed(2)}%</strong>
            </span>
            <span>
              Clips curados: <strong className="font-mono text-amber-300">{summary?.total_clips_rendered ?? 0}</strong>
            </span>
          </div>
        </div>

        {/* Card 3: Tokens Totales */}
        <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-900/75 p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Tokens Procesados</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-400/15 text-sky-300">
              <Sparkles className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-50">
              {(summary?.total_tokens ?? 0).toLocaleString("es-CO")}
            </span>
            <span className="text-xs font-bold text-slate-400">tokens</span>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5 text-xs text-slate-400">
            <span>
              In: <strong className="font-mono text-slate-200">{(summary?.input_tokens ?? 0).toLocaleString("es-CO")}</strong>
            </span>
            <span>
              Out:{" "}
              <strong className="font-mono text-sky-300">{(summary?.output_tokens ?? 0).toLocaleString("es-CO")}</strong>
            </span>
          </div>
        </div>

        {/* Card 4: Horas de Audio Facturadas */}
        <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-900/75 p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Audio Facturado (STT)</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-400/15 text-violet-300">
              <Headphones className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-50">
              {(summary?.audio_hours_billed ?? 0).toFixed(2)}
            </span>
            <span className="text-xs font-bold text-slate-400">
              horas ({(summary?.audio_minutes_billed ?? 0).toFixed(1)} min)
            </span>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5 text-xs text-slate-400">
            <span>
              Llamadas API: <strong className="font-mono text-slate-200">{summary?.total_calls ?? 0}</strong> ({summary?.stt_calls ?? 0} STT · {summary?.llm_calls ?? 0} LLM)
            </span>
            <span>
              Latencia X̄: <strong className="font-mono text-slate-200">{summary?.avg_latency_ms ?? 0} ms</strong>
            </span>
          </div>
        </div>
      </div>

      {/* 2. Reactive Budget Bar & Capacity Estimation Banner */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Progress & Alert Panel */}
        <div className={`rounded-3xl border p-6 shadow-xl lg:col-span-7 ${alertMeta.panelClass}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-100">Estado del Tope de Presupuesto</h2>
              <p className="mt-0.5 text-xs text-slate-300/90">{alertMeta.description}</p>
            </div>
            <span className="font-mono text-sm font-black text-slate-100">
              ${(summary?.spent_usd ?? 0).toFixed(4)} / ${(summary?.max_budget_usd ?? 9.0).toFixed(2)} USD (
              {(summary?.usage_pct ?? 0).toFixed(2)}%)
            </span>
          </div>

          {/* Reactive Progress Bar */}
          <div className="relative mt-5">
            <div className="h-4 w-full overflow-hidden rounded-full bg-slate-950/80 p-0.5 ring-1 ring-white/10">
              <div
                className={`h-full rounded-full bg-gradient-to-r transition-all duration-700 ${alertMeta.barClass}`}
                style={{ width: `${Math.max(1.5, usagePct)}%` }}
              />
            </div>
            {/* Threshold markers: 70% Warning, 90% Critical */}
            <div className="mt-2 flex items-center justify-between text-[11px] font-semibold text-slate-400">
              <span>0% ($0.00)</span>
              <span className="text-emerald-300">Normal &lt; 70%</span>
              <span className="text-amber-300">Advertencia 70%</span>
              <span className="text-rose-300">Crítico 90%</span>
              <span>100% (${(summary?.max_budget_usd ?? 9.0).toFixed(2)})</span>
            </div>
          </div>

          {/* Unit cost metrics */}
          <div className="mt-5 grid grid-cols-1 gap-3 border-t border-white/10 pt-4 sm:grid-cols-3">
            <div className="rounded-2xl bg-slate-950/60 px-3.5 py-2.5 ring-1 ring-white/5">
              <span className="block text-[11px] text-slate-400">Costo Promedio / Hora Stream</span>
              <span className="font-mono text-base font-black text-amber-300">
                ${(summary?.projections.avg_cost_per_stream_hour_usd ?? 0.2674).toFixed(4)} USD/h
              </span>
            </div>
            <div className="rounded-2xl bg-slate-950/60 px-3.5 py-2.5 ring-1 ring-white/5">
              <span className="block text-[11px] text-slate-400">Costo Promedio / Clip Curado</span>
              <span className="font-mono text-base font-black text-emerald-300">
                ${(summary?.projections.avg_cost_per_clip_usd ?? 0.0888).toFixed(4)} USD/clip
              </span>
            </div>
            <div className="rounded-2xl bg-slate-950/60 px-3.5 py-2.5 ring-1 ring-white/5">
              <span className="block text-[11px] text-slate-400">Rendimiento Promedio</span>
              <span className="font-mono text-base font-black text-sky-300">
                {(summary?.projections.avg_clips_per_stream_hour ?? 3.0).toFixed(1)} clips / hora
              </span>
            </div>
          </div>
        </div>

        {/* Capacity Estimation Banner */}
        <div className="flex flex-col justify-between rounded-3xl border border-amber-400/25 bg-gradient-to-br from-amber-500/15 via-slate-900/90 to-slate-950 p-6 shadow-xl lg:col-span-5">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-400/15 px-3 py-1 text-xs font-extrabold text-amber-200">
              <TrendingUp className="h-3.5 w-3.5" />
              Proyección de Capacidad Disponible
            </div>
            <p className="mt-4 text-lg font-extrabold leading-snug text-slate-100">
              Con tu saldo actual (
              <span className="font-mono text-amber-300">~${(summary?.remaining_usd ?? 8.56).toFixed(2)} USD</span>)
              puedes procesar aproximadamente{" "}
              <span className="font-mono text-emerald-300 underline decoration-emerald-400/50 decoration-wavy underline-offset-4">
                {(summary?.projections.estimated_remaining_stream_hours ?? 32.0).toFixed(1)} horas
              </span>{" "}
              de stream más.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              Equivale a generar aproximadamente{" "}
              <strong className="font-mono text-amber-200">
                ~{summary?.projections.estimated_remaining_clips ?? 96} clips verticales 9:16
              </strong>{" "}
              adicionales manteniendo tu configuración actual (Deepgram Nova-3 + Gemini 3.5 Flash-Lite).
            </p>
          </div>

          <div className="mt-5 flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-xs">
            <div className="flex items-center gap-2 text-slate-300">
              <Zap className="h-4 w-4 text-amber-300" />
              <span>Re-ejecutar sesiones ya cacheadas:</span>
            </div>
            <span className="rounded-full bg-emerald-500/20 px-2.5 py-0.5 font-mono font-bold text-emerald-300">
              $0.00 USD (Gratis)
            </span>
          </div>
        </div>
      </div>

      {/* 2b. Comparativa de Consumo Actual vs Capa Gratuita (Estilo Google AI Studio Rate Limit & Free Tier) */}
      {summary?.free_tier && summary.free_tier.models.length > 0 && (() => {
        const ftModels = summary.free_tier.models;
        const activeFt: AnalyticsFreeTierModel =
          ftModels.find((m) => m.id === selectedFreeTierModelId) ?? ftModels[0];

        return (
          <div className="mb-8 rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-xl">
            {/* Top Bar — AI Studio Style */}
            <div className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 sm:flex-row sm:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-lg font-black tracking-tight text-slate-50">
                    Límites y Progreso frente a Capa Gratuita (API Rate Limits)
                  </h2>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/35 bg-emerald-500/15 px-3 py-0.5 text-xs font-extrabold text-emerald-300">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]" />
                    Free tier activo
                  </span>
                  <span className="rounded-lg border border-white/10 bg-slate-950/80 px-2.5 py-0.5 font-mono text-[11px] text-slate-300">
                    Rango: Último 1 Día (24h)
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Uso pico por modelo comparado contra el límite de tu capa gratuita (RPM, TPM y RPD), idéntico al monitor de Google AI Studio.
                </p>
              </div>

              {/* Selector de modelo para las gráficas de tendencia */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-400">Modelo en gráficas:</span>
                <select
                  value={activeFt.id}
                  onChange={(e) => setSelectedFreeTierModelId(e.target.value)}
                  aria-label="Seleccionar modelo para gráficas de capa gratuita"
                  className="rounded-xl border border-white/15 bg-slate-950 px-3 py-1.5 text-xs font-bold text-slate-100 focus:border-amber-400 focus:outline-none"
                >
                  {ftModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name} ({m.tier_name})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Rate limits by model table */}
            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/10 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    <th className=" pb-3 pr-4">Modelo</th>
                    <th className="px-4 pb-3">Categoría / Plan</th>
                    <th className="px-4 pb-3" title="Peticiones pico por minuto vs límite gratuito">
                      RPM ↓ (Peticiones/min)
                    </th>
                    <th className="px-4 pb-3" title="Tokens de entrada o segundos de audio pico por minuto">
                      TPM / Audio por min
                    </th>
                    <th className="px-4 pb-3" title="Peticiones acumuladas en el día vs cuota diaria gratuita">
                      RPD (Peticiones/día)
                    </th>
                    <th className="pl-4 pb-3 text-right">Estado en Capa Gratuita</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {ftModels.map((m) => {
                    const isSelected = m.id === activeFt.id;
                    return (
                      <tr
                        key={m.id}
                        onClick={() => setSelectedFreeTierModelId(m.id)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                        }`}
                      >
                        <td className="whitespace-nowrap py-3.5 pr-4">
                          <div className="flex items-center gap-2">
                            <span
                              className={`h-2 w-2 rounded-full ${
                                isSelected ? "bg-amber-400" : "bg-slate-600"
                              }`}
                            />
                            <span className="font-bold text-slate-100">{m.display_name}</span>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3.5 text-slate-400">
                          <div>{m.category}</div>
                          <div className="text-[10px] font-semibold text-slate-500">{m.tier_name}</div>
                        </td>
                        <td className="px-4 py-3.5">
                          <AiStudioProgressCell used={m.rpm.peak} limit={m.rpm.limit} />
                        </td>
                        <td className="px-4 py-3.5">
                          <AiStudioProgressCell
                            used={m.tpm.peak}
                            limit={m.tpm.limit}
                            formatValue={formatCompactMetric}
                          />
                        </td>
                        <td className="px-4 py-3.5">
                          <AiStudioProgressCell
                            used={m.rpd.used}
                            limit={m.rpd.limit}
                            formatValue={formatCompactMetric}
                          />
                        </td>
                        <td className="whitespace-nowrap py-3.5 pl-4 text-right">
                          {m.zero_cost_in_free_tier && m.within_free_tier ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-500/15 px-2.5 py-1 font-mono text-[11px] font-bold text-emerald-300">
                              100% Cubierto · $0.00
                            </span>
                          ) : m.credit.limit_usd > 0 ? (
                            <div className="inline-flex flex-col items-end">
                              <span className="font-mono text-xs font-bold text-emerald-300">
                                ${m.credit.remaining_usd.toFixed(2)} / ${m.credit.limit_usd.toFixed(0)} libres
                              </span>
                              <span className="text-[10px] text-slate-400">
                                Usado {m.credit.pct.toFixed(2)}% del crédito gratis
                              </span>
                            </div>
                          ) : (
                            <span className="rounded-full bg-amber-500/15 px-2.5 py-1 font-mono text-[11px] font-bold text-amber-300">
                              Pay-as-you-go
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* 3 Peak usage trends charts with red dashed Limit line (AI Studio style) */}
            <div className="mt-6 border-t border-white/10 pt-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider text-slate-300">
                    Tendencias de Uso Pico vs Límite de Capa Gratuita
                  </span>
                  <span className="rounded-md bg-amber-400/15 px-2 py-0.5 font-mono text-xs font-bold text-amber-300">
                    {activeFt.display_name}
                  </span>
                </div>
                <span className="text-[11px] text-slate-400">
                  La línea punteada roja (<span className="font-bold text-rose-400">Limit</span>) marca el tope de la capa gratuita.
                </span>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                {/* Chart 1: Peak RPM */}
                <AiStudioPeakChartCard
                  title="Peak requests per minute (RPM)"
                  limit={activeFt.rpm.limit}
                  peakValue={activeFt.rpm.peak}
                  series={activeFt.timeline_24h.map((p) => ({ label: p.label, value: p.peak_rpm }))}
                  formatAxis={(v) => String(Math.round(v))}
                />

                {/* Chart 2: Peak TPM / Audio per min */}
                <AiStudioPeakChartCard
                  title={
                    activeFt.tpm.unit === "tok"
                      ? "Peak input tokens per minute (TPM)"
                      : "Pico de audio procesado por minuto (seg)"
                  }
                  limit={activeFt.tpm.limit}
                  peakValue={activeFt.tpm.peak}
                  series={activeFt.timeline_24h.map((p) => ({ label: p.label, value: p.peak_tpm }))}
                  formatAxis={formatCompactMetric}
                />

                {/* Chart 3: Peak RPD */}
                <AiStudioPeakChartCard
                  title="Peak requests per day (RPD)"
                  limit={activeFt.rpd.limit}
                  peakValue={activeFt.rpd.used}
                  series={activeFt.timeline_24h.map((p) => ({ label: p.label, value: p.cumulative_rpd }))}
                  formatAxis={formatCompactMetric}
                />
              </div>
            </div>
          </div>
        );
      })()}

      {/* 3. Visual Breakdown (Providers + Tokens/Calls) & Interactive Cost Simulator */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Visual Provider & Token Breakdown */}
        <div className="rounded-3xl border border-white/10 bg-slate-900/75 p-6 shadow-xl lg:col-span-7">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-base font-bold text-slate-100">
                <Layers className="h-4 w-4 text-amber-300" />
                Desglose Visual por Proveedor y Modelo
              </h2>
              <p className="text-xs text-slate-400">
                Comparativa directa de inversión, llamadas, audio transcripto y tokens entre proveedores.
              </p>
            </div>
          </div>

          {/* Provider Bars */}
          <div className="mt-5 space-y-4">
            {providerComparison.map((prov) => {
              const meta = getProviderMeta(prov.provider);
              const barWidth = prov.cost_usd > 0 ? Math.max(4, prov.share_pct) : 0;
              return (
                <div
                  key={prov.provider}
                  className="rounded-2xl border border-white/5 bg-slate-950/60 p-4 transition-colors hover:border-white/15"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`inline-flex items-center rounded-lg border px-2.5 py-0.5 text-xs font-extrabold ${meta.badgeBg} ${meta.badgeText} ${meta.border}`}
                      >
                        {meta.label}
                      </span>
                      <span className="text-xs font-semibold uppercase text-slate-400">
                        {prov.kinds.join(" / ")} · {prov.calls} {prov.calls === 1 ? "llamada" : "llamadas"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm font-black text-slate-100">
                        ${prov.cost_usd.toFixed(6)} USD
                      </span>
                      <span className="rounded-full bg-white/10 px-2 py-0.5 font-mono text-[11px] font-bold text-slate-200">
                        {prov.share_pct.toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  {/* Bar */}
                  <div className="mt-2.5 h-2.5 w-full overflow-hidden rounded-full bg-slate-900">
                    <div
                      className={`h-full rounded-full bg-gradient-to-r transition-all duration-700 ${meta.colorBar}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>

                  {/* Metrics footer */}
                  <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                    <span>
                      {prov.audio_minutes > 0
                        ? `Audio facturado: ${prov.audio_minutes.toFixed(2)} min (${(prov.audio_minutes / 60).toFixed(2)} h)`
                        : prov.total_tokens > 0
                        ? `Tokens procesados: ${prov.total_tokens.toLocaleString("es-CO")} tokens`
                        : "Sin consumo registrado aún"}
                    </span>
                    {prov.avg_latency_ms > 0 && (
                      <span className="font-mono text-slate-400">Latencia media: {prov.avg_latency_ms} ms</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Token Input vs Output & Calls Split */}
          <div className="mt-6 grid grid-cols-1 gap-4 border-t border-white/10 pt-5 sm:grid-cols-2">
            {/* Tokens Input vs Output */}
            <div className="rounded-2xl border border-white/5 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between text-xs font-bold text-slate-200">
                <span className="flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-sky-400" />
                  Distribución de Tokens LLM
                </span>
                <span className="font-mono text-sky-300">
                  {(summary?.total_tokens ?? 0).toLocaleString("es-CO")} tot.
                </span>
              </div>
              <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-slate-900">
                <div
                  className="bg-indigo-400 transition-all duration-500"
                  style={{ width: `${inputTokPct}%` }}
                  title={`Entrada: ${inputTokPct}%`}
                />
                <div
                  className="bg-cyan-300 transition-all duration-500"
                  style={{ width: `${outputTokPct}%` }}
                  title={`Salida: ${outputTokPct}%`}
                />
              </div>
              <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-400" />
                  Entrada: <strong className="font-mono text-slate-200">{(summary?.input_tokens ?? 0).toLocaleString("es-CO")}</strong> ({inputTokPct}%)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-cyan-300" />
                  Salida: <strong className="font-mono text-slate-200">{(summary?.output_tokens ?? 0).toLocaleString("es-CO")}</strong> ({outputTokPct}%)
                </span>
              </div>
            </div>

            {/* Calls STT vs LLM */}
            <div className="rounded-2xl border border-white/5 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between text-xs font-bold text-slate-200">
                <span className="flex items-center gap-1.5">
                  <Activity className="h-3.5 w-3.5 text-emerald-400" />
                  Llamadas Realizadas por Tipo
                </span>
                <span className="font-mono text-emerald-300">{summary?.total_calls ?? 0} llamadas</span>
              </div>
              <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-slate-900">
                <div
                  className="bg-emerald-400 transition-all duration-500"
                  style={{
                    width: `${
                      summary && summary.total_calls > 0
                        ? Math.round((summary.stt_calls / summary.total_calls) * 100)
                        : 50
                    }%`,
                  }}
                />
                <div
                  className="bg-sky-400 transition-all duration-500"
                  style={{
                    width: `${
                      summary && summary.total_calls > 0
                        ? Math.round((summary.llm_calls / summary.total_calls) * 100)
                        : 50
                    }%`,
                  }}
                />
              </div>
              <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  Voz a Texto (STT): <strong className="font-mono text-slate-200">{summary?.stt_calls ?? 0}</strong> (tramos de 10m)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-sky-400" />
                  Curación (LLM): <strong className="font-mono text-slate-200">{summary?.llm_calls ?? 0}</strong>
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 4. Interactive Cost Simulator / Calculator */}
        <div className="flex flex-col justify-between rounded-3xl border border-white/10 bg-slate-900/75 p-6 shadow-xl lg:col-span-5">
          <div>
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-base font-bold text-slate-100">
                <Calculator className="h-4 w-4 text-amber-300" />
                Calculadora / Simulador de Costos
              </h2>
              <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-0.5 text-[11px] font-bold text-amber-300">
                Pre-vuelo
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Simula cuánto costará procesar una grabación antes de subirla o iniciarla.
            </p>

            {/* Input: Tengo un stream de [ X ] horas */}
            <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/70 p-4">
              <label className="block text-xs font-bold text-slate-200">
                &ldquo;Tengo un stream de{" "}
                <span className="font-mono text-amber-300">{simResult.hours.toFixed(1)}</span> horas&rdquo;
              </label>

              <div className="mt-3 flex items-center gap-3">
                <input
                  type="range"
                  min={0.5}
                  max={12}
                  step={0.5}
                  value={simHours}
                  onChange={(e) => setSimHours(parseFloat(e.target.value) || 1)}
                  className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 accent-amber-400"
                />
                <div className="flex items-center gap-1.5 rounded-xl border border-white/15 bg-slate-900 px-3 py-1.5">
                  <input
                    type="number"
                    min={0.1}
                    max={48}
                    step={0.5}
                    value={simHours}
                    onChange={(e) => setSimHours(Math.max(0.1, parseFloat(e.target.value) || 0.5))}
                    className="w-14 bg-transparent text-right font-mono text-sm font-black text-amber-300 focus:outline-none"
                  />
                  <span className="text-xs font-bold text-slate-400">h</span>
                </div>
              </div>

              {/* Quick preset buttons */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {[1, 1.66, 2, 3, 4, 6, 8].map((h) => (
                  <button
                    key={h}
                    type="button"
                    onClick={() => setSimHours(h)}
                    className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold transition-all ${
                      Math.abs(simHours - h) < 0.05
                        ? "bg-amber-400 text-slate-950"
                        : "bg-white/5 text-slate-300 hover:bg-white/10"
                    }`}
                  >
                    {h === 1.66 ? "1h 40m (Actual)" : `${h}h`}
                  </button>
                ))}
              </div>

              {/* Provider profile selector */}
              <div className="mt-4">
                <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Perfil de Proveedores para el Cálculo
                </label>
                <select
                  value={simProfile}
                  onChange={(e) => setSimProfile(e.target.value as typeof simProfile)}
                  className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-100 focus:border-amber-400 focus:outline-none"
                >
                  <option value="empirical">
                    Tasa Real Observada en Base de Datos ($
                    {(summary?.projections.avg_cost_per_stream_hour_usd ?? 0.2674).toFixed(4)} USD/h)
                  </option>
                  <option value="deepgram_gemini">
                    Deepgram Nova-3 + Gemini 3.5 Flash-Lite (~$0.2674 USD/h)
                  </option>
                  <option value="groq_gemini">
                    Groq Whisper Turbo + Gemini 3.5 Flash-Lite (~$0.0496 USD/h)
                  </option>
                </select>
              </div>
            </div>

            {/* Simulator Results Breakdown */}
            <div className="mt-4 space-y-2.5 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between text-xs text-slate-300">
                <span className="flex items-center gap-1.5">
                  <Mic className="h-3.5 w-3.5 text-emerald-400" />
                  Transcripción STT ({simResult.estChunks} tramos Opus de 10m):
                </span>
                <span className="font-mono font-bold text-emerald-300">${simResult.sttCost.toFixed(4)} USD</span>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-300">
                <span className="flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-sky-400" />
                  Curación LLM (~{simResult.estTokens.toLocaleString("es-CO")} tokens):
                </span>
                <span className="font-mono font-bold text-sky-300">${simResult.llmCost.toFixed(4)} USD</span>
              </div>
              <div className="flex items-center justify-between border-t border-white/10 pt-2.5">
                <span className="text-sm font-extrabold text-slate-100">Costo Total Estimado:</span>
                <span className="font-mono text-xl font-black text-amber-300">
                  ${simResult.totalCost.toFixed(4)} USD
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-400">
                <span>Clips 9:16 esperados: ~{simResult.estClips} clips</span>
                <span>
                  Costo por clip: ~${(simResult.totalCost / Math.max(1, simResult.estClips)).toFixed(4)} USD
                </span>
              </div>
            </div>
          </div>

          {/* Budget validation status for simulated stream */}
          <div
            className={`mt-4 flex items-center justify-between rounded-2xl border px-4 py-3 text-xs font-bold ${
              simResult.fitsBudget
                ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
                : "border-rose-400/40 bg-rose-500/15 text-rose-200"
            }`}
          >
            <span>
              {simResult.fitsBudget
                ? `Cubierto por tu saldo actual. Quedarían $${simResult.remainingAfter.toFixed(2)} USD.`
                : `Excede tu saldo disponible actual ($${(summary?.remaining_usd ?? 0).toFixed(2)} USD).`}
            </span>
            <span className="font-mono uppercase">{simResult.fitsBudget ? "VIABLE" : "SIN SALDO"}</span>
          </div>
        </div>
      </div>

      {/* 4. Session & Model Summary Strip */}
      {breakdown && breakdown.by_session.length > 0 && (
        <div className="mb-8 rounded-3xl border border-white/10 bg-slate-900/75 p-6 shadow-xl">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-base font-bold text-slate-100">
                <Calendar className="h-4 w-4 text-amber-300" />
                Consumo Agrupado por Sesión y Día
              </h2>
              <p className="text-xs text-slate-400">
                Trazabilidad de cuánto costó cada sesión de grabación y cuántos clips produjo.
              </p>
            </div>
            {breakdown.by_day.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {breakdown.by_day.map((d) => (
                  <span
                    key={d.date}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/80 px-3 py-1 text-xs text-slate-300"
                  >
                    <Clock className="h-3 w-3 text-amber-300" />
                    <span className="font-mono font-bold">{d.date}</span>: {d.calls} llamadas ·{" "}
                    <strong className="font-mono text-amber-300">${d.cost_usd.toFixed(4)} USD</strong>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {breakdown.by_session.map((s) => (
              <div
                key={s.session_id}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-slate-950/60 p-4 sm:flex-row sm:items-center"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/sessions/${s.session_id}`}
                      className="inline-flex items-center gap-1 font-bold text-slate-100 transition-colors hover:text-amber-300"
                    >
                      {s.session_title}
                      <ArrowUpRight className="h-3.5 w-3.5" />
                    </Link>
                    <span className="rounded-md bg-white/10 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                      {s.session_id}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {s.calls} llamadas ({s.stt_calls} STT · {s.llm_calls} LLM) · {s.audio_minutes.toFixed(1)} min audio ·{" "}
                    {s.total_tokens.toLocaleString("es-CO")} tokens ·{" "}
                    <strong className="text-emerald-300">{s.clips_count} clips generados</strong>
                  </p>
                </div>
                <div className="mt-3 text-left sm:mt-0 sm:text-right">
                  <span className="block font-mono text-base font-black text-amber-300">
                    ${s.cost_usd.toFixed(6)} USD
                  </span>
                  <span className="text-[11px] text-slate-400">
                    ${s.cost_per_clip_usd.toFixed(4)} USD / clip
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Detailed Audit & Traceability Table */}
      <div className="rounded-3xl border border-white/10 bg-slate-900/75 p-6 shadow-xl">
        <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div>
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-100">
              <Filter className="h-4 w-4 text-amber-300" />
              Tabla de Auditoría y Trazabilidad Detallada (`api_calls`)
            </h2>
            <p className="text-xs text-slate-400">
              Cada petición individual a proveedores externos con su hash de caché, duración/tokens, latencia y costo exacto.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-white/10 bg-slate-950/70 px-3 py-1.5 text-slate-300">
              Registros filtrados: <strong className="font-mono text-slate-100">{logsData?.total ?? 0}</strong>
            </span>
            <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1.5 text-amber-200">
              Subtotal filtrado:{" "}
              <strong className="font-mono">${(logsData?.filtered_cost_usd ?? 0).toFixed(6)} USD</strong>
            </span>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {/* Search */}
          <div className="relative lg:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleFilterChange(setSearchQuery, e.target.value)}
              placeholder="Buscar por modelo, sesión, ID o hash..."
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 py-2 pl-9 pr-3 text-xs text-slate-100 placeholder-slate-500 focus:border-amber-400 focus:outline-none"
            />
          </div>

          {/* Provider filter */}
          <div>
            <select
              value={filterProvider}
              onChange={(e) => handleFilterChange(setFilterProvider, e.target.value)}
              aria-label="Filtrar por proveedor"
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-slate-200 focus:border-amber-400 focus:outline-none"
            >
              <option value="all">Proveedor: Todos</option>
              <option value="deepgram">Deepgram</option>
              <option value="gemini">Google Gemini</option>
              <option value="groq">Groq Cloud</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>

          {/* Kind filter */}
          <div>
            <select
              value={filterKind}
              onChange={(e) => handleFilterChange(setFilterKind, e.target.value)}
              aria-label="Filtrar por tipo de llamada"
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-slate-200 focus:border-amber-400 focus:outline-none"
            >
              <option value="all">Tipo: Todos (STT + LLM)</option>
              <option value="stt">Voz a Texto (STT)</option>
              <option value="llm">Curación Narrativa (LLM)</option>
            </select>
          </div>

          {/* Session filter */}
          <div>
            <select
              value={filterSession}
              onChange={(e) => handleFilterChange(setFilterSession, e.target.value)}
              aria-label="Filtrar por sesión"
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-slate-200 focus:border-amber-400 focus:outline-none"
            >
              <option value="all">Sesión: Todas</option>
              {(breakdown?.by_session ?? []).map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  {s.session_title} ({s.session_id})
                </option>
              ))}
            </select>
          </div>

          {/* Date filter */}
          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={filterDateFrom}
              onChange={(e) => handleFilterChange(setFilterDateFrom, e.target.value)}
              title="Fecha desde"
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-2.5 py-2 text-xs text-slate-200 focus:border-amber-400 focus:outline-none"
            />
            {(filterProvider !== "all" ||
              filterKind !== "all" ||
              filterSession !== "all" ||
              filterDateFrom ||
              filterDateTo ||
              searchQuery) && (
              <button
                type="button"
                onClick={() => {
                  setFilterProvider("all");
                  setFilterKind("all");
                  setFilterSession("all");
                  setFilterDateFrom("");
                  setFilterDateTo("");
                  setSearchQuery("");
                  setPageOffset(0);
                }}
                className="shrink-0 rounded-xl border border-white/10 bg-white/5 px-2.5 py-2 text-xs font-bold text-slate-300 hover:bg-white/10"
              >
                Limpiar
              </button>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/60">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 bg-slate-950/90 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                <th className="px-4 py-3.5">Fecha / Hora</th>
                <th className="px-4 py-3.5">Proveedor</th>
                <th className="px-4 py-3.5">Modelo / Tipo</th>
                <th className="px-4 py-3.5">Duración / Tokens</th>
                <th className="px-4 py-3.5 text-right">Costo ($USD)</th>
                <th className="px-4 py-3.5 text-right">Latencia</th>
                <th className="px-4 py-3.5">Sesión Vinculada</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading && !logsData ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-400">
                    Cargando historial de llamadas a APIs...
                  </td>
                </tr>
              ) : (logsData?.items.length ?? 0) === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-400">
                    No se encontraron llamadas a APIs con los filtros seleccionados.
                  </td>
                </tr>
              ) : (
                logsData!.items.map((item) => {
                  const pMeta = getProviderMeta(item.provider);
                  return (
                    <tr key={item.id} className="transition-colors hover:bg-white/[0.03]">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-300">
                        <div>{formatDateTime(item.created_at, item.created_iso)}</div>
                        <div className="text-[10px] text-slate-500">
                          {item.id} · hash {item.task_hash.slice(0, 10)}…
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-lg border px-2.5 py-0.5 text-xs font-extrabold ${pMeta.badgeBg} ${pMeta.badgeText} ${pMeta.border}`}
                        >
                          {pMeta.label}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="font-mono font-bold text-slate-100">{item.model}</div>
                        <span
                          className={`mt-0.5 inline-block rounded px-1.5 py-0.2 text-[10px] font-bold uppercase ${
                            item.kind === "stt"
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-sky-500/15 text-sky-300"
                          }`}
                        >
                          {item.kind === "stt" ? "STT · Audio" : "LLM · Curación"}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-200">
                        {item.kind === "stt" ? (
                          <div>
                            <span className="font-bold text-emerald-300">{item.audio_minutes.toFixed(2)} min</span>{" "}
                            <span className="text-slate-400">({item.audio_seconds.toFixed(1)}s)</span>
                          </div>
                        ) : (
                          <div>
                            <span className="font-bold text-sky-300">
                              {item.total_tokens.toLocaleString("es-CO")} tok
                            </span>{" "}
                            <span className="text-slate-400">
                              ({item.input_tokens.toLocaleString("es-CO")} in /{" "}
                              {item.output_tokens.toLocaleString("es-CO")} out)
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-sm font-black text-amber-300">
                        ${item.cost_usd.toFixed(6)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-slate-300">
                        {item.latency_ms.toLocaleString("es-CO")} ms
                      </td>
                      <td className="px-4 py-3">
                        {item.session_id ? (
                          <Link
                            href={`/sessions/${item.session_id}`}
                            className="inline-flex items-center gap-1 font-semibold text-slate-200 transition-colors hover:text-amber-300"
                          >
                            <span className="truncate max-w-[210px]">
                              {item.session_title || item.session_id}
                            </span>
                            <ArrowUpRight className="h-3 w-3 shrink-0" />
                          </Link>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {logsData && logsData.total > pageLimit && (
          <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
            <span>
              Mostrando {logsData.offset + 1} – {Math.min(logsData.offset + pageLimit, logsData.total)} de{" "}
              {logsData.total} llamadas
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={pageOffset === 0}
                onClick={() => setPageOffset(Math.max(0, pageOffset - pageLimit))}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 font-bold text-slate-200 disabled:opacity-40"
              >
                Anterior
              </button>
              <button
                type="button"
                disabled={pageOffset + pageLimit >= logsData.total}
                onClick={() => setPageOffset(pageOffset + pageLimit)}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 font-bold text-slate-200 disabled:opacity-40"
              >
                Siguiente
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
