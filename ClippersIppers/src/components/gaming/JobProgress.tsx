"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import type { WorkerJob } from "@/types/gaming";
import { STAGE_LABELS } from "@/lib/workerClient";
import { Disclosure, ProgressBar, SoftSpinner } from "./ui";

// Calm progress for a single job: spinner + label + thin gold bar. Errors show a
// short message; the traceback stays behind "Detalles técnicos".
export function JobProgress({ job, compact = false }: { job: WorkerJob; compact?: boolean }) {
  const label = STAGE_LABELS[job.stage] || job.stage || "En cola";

  if (job.status === "error") {
    return (
      <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        <p className="flex items-center gap-2 font-bold">
          <AlertTriangle className="h-4 w-4 shrink-0" /> Algo falló en «{label}»
        </p>
        <p className="mt-1 break-words text-xs text-rose-200/80">{job.error}</p>
        {!compact && job.message && (
          <Disclosure title={<span className="text-xs text-rose-200/80">Detalles técnicos</span>} className="mt-2">
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950/60 p-3 font-mono text-[11px] text-slate-400">
              {job.message}
            </pre>
          </Disclosure>
        )}
      </div>
    );
  }

  if (job.status === "done") return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2.5 font-bold text-slate-200">
          <SoftSpinner className="h-4 w-4 shrink-0" />
          <span className="truncate">{job.status === "queued" ? "En cola" : label}</span>
        </span>
        <span className="font-extrabold tabular-nums text-amber-300">{Math.round(job.progress * 100)}%</span>
      </div>
      <ProgressBar value={job.progress} />
      {!compact && job.message && <p className="truncate text-xs text-slate-400">{job.message}</p>}
    </div>
  );
}
