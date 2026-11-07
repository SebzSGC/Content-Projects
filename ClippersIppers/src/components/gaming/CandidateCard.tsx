"use client";

import React, { useState } from "react";
import { Clapperboard, Copy, Check, ShieldCheck, SlidersHorizontal } from "lucide-react";
import type { Candidate, WorkerJob } from "@/types/gaming";
import { formatClock } from "@/lib/workerClient";
import { JobProgress } from "./JobProgress";
import { Badge, Disclosure, GlassCard, InfoTip, btnGhost, btnPrimary, inputBase } from "./ui";

export interface CandidateEdits {
  start: number;
  end: number;
  overlay_title: string;
}

// What matters first: the publish title, the score and the "Crear Short" action.
// Score breakdown, reviewer notes and the trim/title editor are one click away.
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
  const busy = Boolean(job && (job.status === "queued" || job.status === "running"));
  const score = Math.round(candidate.final_score);

  const copyPost = async () => {
    const text = `${candidate.post_title}\n${candidate.hashtags.map((h) => `#${h}`).join(" ")}`;
    await navigator.clipboard.writeText(text).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <GlassCard as="article" interactive={!busy} className={`flex flex-col gap-4 p-5 ${busy ? "ring-2 ring-amber-400/30" : ""}`}>
      <div className="flex items-start gap-4">
        <div className="flex shrink-0 flex-col items-center">
          <span
            className={`flex h-14 w-14 items-center justify-center rounded-full text-xl font-black tabular-nums ${
              score >= 75
                ? "bg-amber-400 text-slate-950 shadow-lg shadow-amber-500/25"
                : score >= 55
                  ? "bg-amber-400/15 text-amber-300"
                  : "bg-white/5 text-slate-300"
            }`}
          >
            {score}
          </span>
          <span className="mt-1 flex items-center text-[10px] font-bold uppercase tracking-wide text-slate-500">
            puntaje
            <InfoTip label="Cómo se calcula el puntaje">
              IA: {Math.round(candidate.llm_score)} · Señales: {Math.round(candidate.signal_score * 100)}
              {candidate.verify_score != null ? ` · Revisión: ${Math.round(candidate.verify_score)}` : ""}
              <br />
              Combina la opinión de la IA con las risas, gritos y reacciones detectadas.
            </InfoTip>
          </span>
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge>#{rank}</Badge>
            <Badge>
              {formatClock(candidate.start)} – {formatClock(candidate.end)} · {Math.round(candidate.end - candidate.start)} s
            </Badge>
            {candidate.verified && (
              <Badge tone="success">
                <ShieldCheck className="h-3 w-3" /> Revisado
              </Badge>
            )}
          </div>
          <h3 className="text-base font-extrabold leading-snug text-slate-50">{candidate.post_title || candidate.overlay_title}</h3>
          <p className="text-sm text-slate-400">
            En pantalla: <span className="font-semibold text-slate-300">{overlay || "—"}</span>
          </p>
        </div>
      </div>

      {candidate.reason && <p className="line-clamp-2 text-sm leading-relaxed text-slate-400">{candidate.reason}</p>}

      {candidate.hashtags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {candidate.hashtags.map((h) => (
            <span key={h} className="rounded-full bg-white/5 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
              #{h}
            </span>
          ))}
        </div>
      )}

      {busy && job ? (
        <JobProgress job={job} compact />
      ) : (
        job?.status === "error" && <JobProgress job={job} compact />
      )}

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <button onClick={() => onRender({ start, end, overlay_title: overlay })} disabled={busy || end - start < 1} className={btnPrimary}>
          <Clapperboard className="h-4 w-4" />
          {busy ? "Creando…" : "Crear Short"}
        </button>
        <button onClick={copyPost} className={btnGhost}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-300" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copiado" : "Copiar título"}
        </button>
      </div>

      <Disclosure title="Ajustar clip" subtitle="Título en pantalla, inicio y fin" icon={<SlidersHorizontal className="h-4 w-4" />} className="border-t border-white/5 pt-3">
        <div className="space-y-3">
          <label className="block space-y-1.5">
            <span className="text-xs font-bold text-slate-400">Título en pantalla</span>
            <input value={overlay} onChange={(e) => setOverlay(e.target.value)} className={inputBase} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-xs font-bold text-slate-400">Inicio (s)</span>
              <input type="number" step={0.1} value={start} onChange={(e) => setStart(Number(e.target.value))} className={`${inputBase} font-mono`} />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs font-bold text-slate-400">Fin (s)</span>
              <input type="number" step={0.1} value={end} onChange={(e) => setEnd(Number(e.target.value))} className={`${inputBase} font-mono`} />
            </label>
          </div>
          {candidate.verification_notes && (
            <p className="rounded-2xl bg-white/5 px-3 py-2 text-xs italic text-slate-400">Nota del revisor: {candidate.verification_notes}</p>
          )}
        </div>
      </Disclosure>
    </GlassCard>
  );
}
