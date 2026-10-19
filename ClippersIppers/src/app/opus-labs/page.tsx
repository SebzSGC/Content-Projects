"use client";

import React, { useState } from "react";
import { useAtom } from "jotai";
import { cpuBenchmarkAtom, statsigGatesAtom } from "@/store/opusStore";
import { runCpuBenchmark } from "@/lib/cpuBenchmark";
import {
  FlaskConical,
  Cpu,
  Sliders,
  Play,
  CheckCircle2,
  Code2,
} from "lucide-react";

export default function OpusLabsPage() {
  const [gates, setGates] = useAtom(statsigGatesAtom);
  const [benchmark, setBenchmark] = useAtom(cpuBenchmarkAtom);
  const [runningBench, setRunningBench] = useState(false);

  const handleRunCpuBenchmark = async () => {
    setRunningBench(true);
    const res = await runCpuBenchmark();
    setBenchmark(res);
    setRunningBench(false);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-8">
      <div className="border-b border-[var(--border)] pb-4">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <FlaskConical className="h-5 w-5 text-purple-400" />
          <span>Opus Labs — REA Statsig Gates &amp; Web Worker CPU Benchmark</span>
        </h1>
        <p className="text-xs text-[var(--muted-foreground)]">
          Panel de ingeniería inversa para conmutar en caliente los Feature Gates de Statsig extraídos de los chunks de Turbopack y ejecutar el benchmark de CPU (`Módulo 681368`).
        </p>
      </div>

      {/* 1. Web Worker CPU Benchmark (Module 681368) */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Cpu className="h-4 w-4 text-[var(--primary)]" />
              <span>1. Web Worker CPU Benchmark (`Módulo 681368: runCpuBenchmark`)</span>
            </h2>
            <p className="text-xs text-[var(--muted-foreground)]">
              Ejecuta un bucle intensivo `Math.imul + Math.sin` durante ~60ms en un hilo `Worker` aislado (`Blob URL`) para calibrar el rendimiento de decodificación NLE del navegador.
            </p>
          </div>

          <button
            onClick={handleRunCpuBenchmark}
            disabled={runningBench}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-4 py-2.5 text-xs font-bold text-black hover:opacity-95 transition shrink-0 cursor-pointer disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            <span>
              {runningBench ? "Ejecutando Worker..." : "Ejecutar Benchmark CPU"}
            </span>
          </button>
        </div>

        {benchmark && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
              <div className="text-[10px] uppercase text-[var(--muted-foreground)]">
                Score
              </div>
              <div className="text-lg font-black text-[var(--primary)]">
                {benchmark.score} ops/ms
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
              <div className="text-[10px] uppercase text-[var(--muted-foreground)]">
                Hardware Tier
              </div>
              <div className="text-lg font-black uppercase text-emerald-400">
                {benchmark.tier}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
              <div className="text-[10px] uppercase text-[var(--muted-foreground)]">
                Logical Cores
              </div>
              <div className="text-lg font-black">{benchmark.cores}</div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
              <div className="text-[10px] uppercase text-[var(--muted-foreground)]">
                Iterations
              </div>
              <div className="text-lg font-mono font-bold">
                {benchmark.iterations.toLocaleString()}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
              <div className="text-[10px] uppercase text-[var(--muted-foreground)]">
                Duration
              </div>
              <div className="text-lg font-mono font-bold">
                {benchmark.durationMs} ms
              </div>
            </div>
          </div>
        )}
      </section>

      {/* 2. Statsig Feature Gates & Experiments Live Toggle */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold flex items-center gap-2">
          <Sliders className="h-4 w-4 text-[var(--primary)]" />
          <span>2. Live Statsig Feature Gates &amp; Experiments ({gates.length})</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {gates.map((gate) => (
            <div
              key={gate.key}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col justify-between space-y-3"
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <code className="rounded bg-[var(--secondary)] px-2 py-0.5 text-xs font-bold text-[var(--primary)]">
                    {gate.key}
                  </code>
                  <span className="text-[11px] font-mono text-[var(--muted-foreground)]">
                    Módulo {gate.moduleId}
                  </span>
                </div>
                <h3 className="text-sm font-bold">{gate.name}</h3>
                <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">
                  {gate.description}
                </p>
              </div>

              <div className="border-t border-[var(--border)] pt-3 flex items-center justify-between">
                <span className="text-[11px] text-[var(--muted-foreground)]">
                  Variante: <strong className="text-[var(--foreground)]">{gate.variant}</strong>
                </span>
                <button
                  onClick={() =>
                    setGates((prev) =>
                      prev.map((g) =>
                        g.key === gate.key ? { ...g, enabled: !g.enabled } : g
                      )
                    )
                  }
                  className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${
                    gate.enabled
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-zinc-700/40 text-zinc-400 border border-zinc-700"
                  }`}
                >
                  {gate.enabled ? "PASS (Enabled)" : "FAIL (Disabled)"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
