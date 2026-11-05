"use client";

import React, { useState } from "react";
import { Clapperboard, Copy, Check, ShieldCheck, Zap, Loader2 } from "lucide-react";
import type { Candidate, WorkerJob } from "@/types/gaming";
import { formatClock } from "@/lib/workerClient";
import { JobProgress } from "./JobProgress";

export interface CandidateEdits {
  start: number;
  end: number;
  overlay_title: string;
}

export function CandidateCard({
  candidate,
  rank,
  job,
  onRender,
}: {
  candidate: Candidate;
  rank: number;
  job?: WorkerJob;
  onRender: (edits: CandidateEdits) => void;
}) {
  const [start, setStart] = useState(candidate.start);
  const [end, setEnd] = useState(candidate.end);
  const [overlay, setOverlay] = useState(candidate.overlay_title);
  const [copied, setCopied] = useState(false);
  const busy = job && (job.status === "queued" || job.status === "running");

  const copyPost = async () => {
    const text = `${candidate.post_title}\n${candidate.hashtags.map((h) => `#${h}`).join(" ")}`;
    await navigator.clipboard.writeText(text).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const scoreTone =
    candidate.final_score >= 75 ? "text-[var(--status-success)]" : candidate.final_score >= 55 ? "text-[var(--status-warn)]" : "text-[var(--muted-foreground)]";

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <p className="text-[11px] font-mono text-[var(--muted-foreground)]">
            #{rank} · {formatClock(candidate.start)} – {formatClock(candidate.end)} · {Math.round(candidate.end - candidate.start)} s
          </p>
          <p className="text-sm font-bold text-[var(--foreground)]">{candidate.post_title || candidate.overlay_title}</p>
        </div>
        <div className="text-right shrink-0">
          <p className={`text-xl font-black leading-none ${scoreTone}`}>{Math.round(candidate.final_score)}</p>
          <p className="text-[10px] text-[var(--muted-foreground)]">puntaje</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 text-[10px] font-semibold">
        <span className="rounded-full bg-[var(--secondary)] px-2 py-0.5 text-[var(--muted-foreground)]">IA {Math.round(candidate.llm_score)}</span>
        <span className="rounded-full bg-[var(--secondary)] px-2 py-0.5 text-[var(--muted-foreground)] inline-flex items-center gap-1">
          <Zap className="h-3 w-3" /> Señales {Math.round(candidate.signal_score * 100)}
        </span>
        {candidate.verified && (
          <span className="rounded-full bg-[var(--status-success-bg)] px-2 py-0.5 text-[var(--status-success)] inline-flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" /> Revisado {Math.round(candidate.verify_score ?? 0)}
          </span>
        )}
        {candidate.hashtags.map((h) => (
          <span key={h} className="rounded-full bg-[var(--primary-subtle)] px-2 py-0.5 text-[var(--primary)]">
            #{h}
          </span>
        ))}
      </div>

      {candidate.reason && <p className="text-xs text-[var(--muted-foreground)]">{candidate.reason}</p>}
      {candidate.verification_notes && <p className="text-xs text-[var(--muted-foreground)] italic">{candidate.verification_notes}</p>}

      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <label className="space-y-1">
          <span className="text-[10px] font-semibold text-[var(--muted-foreground)]">Título en pantalla</span>
          <input
            value={overlay}
            onChange={(e) => setOverlay(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] font-semibold text-[var(--muted-foreground)]">Inicio (s)</span>
          <input
            type="number"
            step={0.1}
            value={start}
            onChange={(e) => setStart(Number(e.target.value))}
            className="w-24 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] font-semibold text-[var(--muted-foreground)]">Fin (s)</span>
          <input
            type="number"
            step={0.1}
            value={end}
            onChange={(e) => setEnd(Number(e.target.value))}
            className="w-24 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => onRender({ start, end, overlay_title: overlay })}
          disabled={busy || end - start < 1}
          className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-white hover:opacity-95 transition cursor-pointer disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />}
          Renderizar Short
        </button>
        <button
          onClick={copyPost}
          className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] hover:border-[var(--primary)] transition cursor-pointer"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          Copiar título y hashtags
        </button>
      </div>
      {job && job.status !== "done" && <JobProgress job={job} />}
    </div>
  );
}
