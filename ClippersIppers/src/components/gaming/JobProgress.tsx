"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import type { WorkerJob } from "@/types/gaming";
import { STAGE_LABELS } from "@/lib/workerClient";

export function JobProgress({ job, compact = false }: { job: WorkerJob; compact?: boolean }) {
  const pct = Math.round(job.progress * 100);
  const label = STAGE_LABELS[job.stage] || job.stage || "En cola";

  if (job.status === "error") {
    return (
      <div className="rounded-xl border border-[var(--status-error)]/30 bg-[var(--status-error-bg)] px-3 py-2 text-xs text-[var(--status-error)] flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-semibold">Falló: {label}</p>
          <p className="break-words opacity-90">{job.error}</p>
        </div>
      </div>
    );
  }

  if (job.status === "done") {
    return compact ? null : (
      <div className="flex items-center gap-2 text-xs text-[var(--status-success)]">
        <CheckCircle2 className="h-4 w-4" />
        <span className="font-semibold">Terminado</span>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-semibold text-[var(--foreground)]">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--primary)]" />
          {job.status === "queued" ? "En cola" : label}
        </span>
        <span className="font-mono text-[var(--muted-foreground)]">{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--secondary)] overflow-hidden">
        <div className="h-full bg-[var(--primary)] transition-all" style={{ width: `${pct}%` }} />
      </div>
      {!compact && job.message && <p className="text-[11px] text-[var(--muted-foreground)] truncate">{job.message}</p>}
    </div>
  );
}
