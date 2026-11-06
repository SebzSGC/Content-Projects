"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  Download,
  Flame,
  Loader2,
  RefreshCw,
  Scissors,
  Sliders,
  StopCircle,
} from "lucide-react";
import {
  API_PREFIX,
  cancelSession,
  fetchSessionClips,
  fetchSessionDetail,
  fetchSessionSignals,
  rerunSession,
  updateManualSync,
  useServerEvents,
  type ClipItem,
  type SessionSummary,
  type SignalSeries,
} from "@/lib/api/client";

const PIPELINE_STEPS = [
  { key: "DOWNLOADED", label: "1. Ingesta" },
  { key: "PREPARED", label: "2. Opus + Sync FFT" },
  { key: "TRANSCRIBED", label: "3. STT + Señales Parquet" },
  { key: "CURATED", label: "4. Curación LLM (IDs)" },
  { key: "PLANNING", label: "5. MediaPipe + EditPlan" },
  { key: "RENDERING", label: "6. Render 1080p NVENC" },
  { key: "DELIVERED", label: "7. Entregado en Salidas/" },
];

function stepIndexForState(state: string): number {
  const idx = PIPELINE_STEPS.findIndex((s) => s.key === state);
  return idx >= 0 ? idx : 0;
}

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = params.id;

  const [session, setSession] = useState<SessionSummary | null>(null);
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [signals, setSignals] = useState<SignalSeries | null>(null);
  const [liveStatus, setLiveStatus] = useState<string>("");
  const [renderProgress, setRenderProgress] = useState<Record<string, number>>({});
  const [manualShift, setManualShift] = useState<string>("0.00");
  const [savingSync, setSavingSync] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [ses, cl, sig] = await Promise.all([
        fetchSessionDetail(sessionId),
        fetchSessionClips(sessionId),
        fetchSessionSignals(sessionId).catch(() => null),
      ]);
      setSession(ses);
      setClips(cl);
      setSignals(sig);
      if (ses.sync) {
        setManualShift(ses.sync.shift_sec.toFixed(3));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId]);

  useEffect(() => {
    reload();
  }, [reload]);

  useServerEvents(sessionId, (ev) => {
    if (ev.message) setLiveStatus(ev.message);
    if (ev.type === "render_progress" && ev.clip_id && typeof ev.progress === "number") {
      setRenderProgress((prev) => ({ ...prev, [ev.clip_id!]: ev.progress! }));
    }
    if (ev.type === "session_state" || ev.type === "clip_updated") {
      reload();
    }
  });

  async function handleSaveSync(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId) return;
    setSavingSync(true);
    setError(null);
    try {
      await updateManualSync(sessionId, parseFloat(manualShift) || 0, 1.0);
      await rerunSession(sessionId);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingSync(false);
    }
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center py-24 text-zinc-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Cargando sesión…
      </div>
    );
  }

  const currentStep = stepIndexForState(session.state);
  const isRunning = !["DELIVERED", "FAILED", "CANCELLED"].includes(session.state);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link href="/sessions" className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white">
            <ArrowLeft className="h-3.5 w-3.5" /> Volver a sesiones
          </Link>
          <h1 className="mt-1 text-2xl font-extrabold text-white">{session.title}</h1>
          <p className="text-xs text-zinc-400">
            ID <code className="text-zinc-300">{session.id}</code> · Estado:{" "}
            <strong className="text-[#FFD400]">{session.state}</strong>
            {session.detected_game ? (
              <>
                {" "}
                · Juego: <strong className="uppercase text-[#39FF14]">{session.detected_game}</strong> (
                {session.keyterms_count ?? 0} keyterms)
              </>
            ) : null}
            {liveStatus ? ` · ${liveStatus}` : ""}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isRunning ? (
            <button
              type="button"
              onClick={() => cancelSession(session.id).then(reload)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/40 bg-red-500/10 px-3.5 py-2 text-xs font-bold text-red-300 hover:bg-red-500/20"
            >
              <StopCircle className="h-4 w-4" /> Cancelar
            </button>
          ) : (
            <button
              type="button"
              onClick={() => rerunSession(session.id).then(reload)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-900 px-3.5 py-2 text-xs font-bold text-white hover:bg-zinc-800"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Re-ejecutar (usa caché SQLite $0)
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}
      {session.error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          Error del pipeline: {session.error}
        </div>
      )}

      {/* 7-Step Pipeline Tracker */}
      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-zinc-800 bg-[#0E1017] p-4 sm:grid-cols-4 lg:grid-cols-7">
        {PIPELINE_STEPS.map((st, idx) => {
          const done = session.state === "DELIVERED" || idx < currentStep;
          const active = session.state !== "DELIVERED" && idx === currentStep && isRunning;
          return (
            <div
              key={st.key}
              className={`rounded-xl border px-3 py-2 text-xs transition ${
                done
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : active
                    ? "border-[#FFD400]/50 bg-[#FFD400]/10 text-[#FFD400]"
                    : "border-zinc-800/80 bg-zinc-950/60 text-zinc-500"
              }`}
            >
              <div className="font-bold">{st.label}</div>
            </div>
          );
        })}
      </div>

      {/* Sync & Signal Excitement Curve */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5">
          <h2 className="flex items-center gap-2 text-sm font-bold text-white">
            <Sliders className="h-4 w-4 text-[#FFD400]" /> Sincronización Juego ↔ Cámara
          </h2>
          {session.sync ? (
            <div className="mt-3 space-y-2 text-xs text-zinc-300">
              <div className="flex justify-between">
                <span className="text-zinc-500">Método:</span>
                <strong className="font-mono text-[#39FF14]">{session.sync.method}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Desfase detectado (shift_sec):</span>
                <strong className="font-mono">{session.sync.shift_sec.toFixed(3)} s</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Confianza FFT:</span>
                <strong>{Math.round(session.sync.confidence * 100)}%</strong>
              </div>
              {session.prepared && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Pista limpia del juego:</span>
                  <strong>
                    {session.prepared.gameplay_clean_audio_stream != null
                      ? `Pista #${session.prepared.gameplay_clean_audio_stream} (Sidechain activo)`
                      : "Mezcla única (EQ voz)"}
                  </strong>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-3 text-xs text-zinc-500">Calculando correlación cruzada de envolventes…</p>
          )}

          <form onSubmit={handleSaveSync} className="mt-4 flex items-end gap-2 border-t border-zinc-800 pt-3">
            <div className="flex-1">
              <label className="mb-1 block text-[11px] text-zinc-400">Ajuste manual shift_sec (s)</label>
              <input
                type="number"
                step="0.05"
                value={manualShift}
                onChange={(e) => setManualShift(e.target.value)}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 font-mono text-xs text-white"
              />
            </div>
            <button
              type="submit"
              disabled={savingSync}
              className="rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700"
            >
              Aplicar
            </button>
          </form>
        </div>

        {/* Signal Excitement Sparkline */}
        <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-bold text-white">
              <Activity className="h-4 w-4 text-[#39FF14]" /> Curva de Emoción Acústica + Movimiento (Parquet)
            </h2>
            {signals && (
              <span className="text-xs text-zinc-400">
                {signals.peaks.length} picos detectados · {Math.round(signals.duration)}s totales
              </span>
            )}
          </div>

          {signals && signals.excitement.length > 1 ? (
            <div className="mt-4">
              <svg viewBox="0 0 800 130" className="h-32 w-full overflow-visible rounded-xl bg-zinc-950/90 p-2">
                {/* Highlight curated clip spans */}
                {clips.map((c) => {
                  const x0 = (c.start / Math.max(1, signals.duration)) * 800;
                  const w = ((c.end - c.start) / Math.max(1, signals.duration)) * 800;
                  return (
                    <rect
                      key={c.id}
                      x={x0}
                      y={0}
                      width={Math.max(4, w)}
                      height={130}
                      fill="rgba(255, 212, 0, 0.12)"
                      stroke="rgba(255, 212, 0, 0.35)"
                    />
                  );
                })}
                {/* Excitement polyline */}
                <polyline
                  fill="none"
                  stroke="#39FF14"
                  strokeWidth="2"
                  points={signals.excitement
                    .map((v, idx) => {
                      const x = (idx / Math.max(1, signals.excitement.length - 1)) * 800;
                      const y = 122 - v * 110;
                      return `${x.toFixed(1)},${y.toFixed(1)}`;
                    })
                    .join(" ")}
                />
                {/* Reaction polyline */}
                <polyline
                  fill="none"
                  stroke="#FFD400"
                  strokeWidth="1.3"
                  strokeDasharray="3,3"
                  points={signals.reaction
                    .map((v, idx) => {
                      const x = (idx / Math.max(1, signals.reaction.length - 1)) * 800;
                      const y = 122 - v * 110;
                      return `${x.toFixed(1)},${y.toFixed(1)}`;
                    })
                    .join(" ")}
                />
                {/* HUD / Killfeed 2fps activity polyline */}
                {signals.hud_activity && signals.hud_activity.length > 1 && (
                  <polyline
                    fill="none"
                    stroke="#38BDF8"
                    strokeWidth="1.4"
                    opacity="0.85"
                    points={signals.hud_activity
                      .map((v, idx) => {
                        const x = (idx / Math.max(1, (signals.hud_activity?.length ?? 2) - 1)) * 800;
                        const y = 122 - v * 110;
                        return `${x.toFixed(1)},${y.toFixed(1)}`;
                      })
                      .join(" ")}
                  />
                )}
              </svg>
              <div className="mt-2 flex flex-wrap items-center gap-5 text-[11px] text-zinc-400">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-[#39FF14]" /> Excitement combinado
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-[#FFD400]" /> Reacción vocal streamer
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-sky-400" /> Actividad HUD / Killfeed (2 fps)
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-4 rounded-sm border border-[#FFD400]/50 bg-[#FFD400]/20" /> Tramos elegidos
                  por el LLM
                </span>
              </div>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-xs text-zinc-500">
              Esperando análisis de señales en CPU…
            </div>
          )}
        </div>
      </div>

      {/* Curated Clips Grid */}
      <div className="space-y-4">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-white">
          <Flame className="h-5 w-5 text-[#FFD400]" /> Clips Curados ({clips.length})
        </h2>

        {clips.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-800 py-14 text-center text-sm text-zinc-500">
            {isRunning
              ? "El pipeline está transcribiendo y curando los mejores momentos…"
              : "No se encontraron clips en esta sesión."}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            {clips.map((clip) => {
              const prog = renderProgress[clip.id];
              const videoUrl = clip.has_final
                ? `${API_PREFIX}/clips/${clip.id}/file?quality=final&t=${Math.floor(clip.updated_at)}`
                : clip.has_draft
                  ? `${API_PREFIX}/clips/${clip.id}/file?quality=draft&t=${Math.floor(clip.updated_at)}`
                  : null;

              return (
                <div
                  key={clip.id}
                  className="flex flex-col justify-between overflow-hidden rounded-2xl border border-zinc-800 bg-[#0E1017] transition hover:border-zinc-700"
                >
                  <div>
                    {/* Vertical 9:16 Player or Poster */}
                    <div className="relative aspect-[9/16] max-h-[420px] w-full bg-black">
                      {videoUrl ? (
                        <video
                          src={videoUrl}
                          controls
                          preload="metadata"
                          className="h-full w-full object-contain"
                        />
                      ) : (
                        <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-xs text-zinc-500">
                          <Loader2 className="h-6 w-6 animate-spin text-[#FFD400]" />
                          <span>Estado: {clip.state}</span>
                          {typeof prog === "number" && <span>Renderizando: {Math.round(prog * 100)}%</span>}
                        </div>
                      )}

                      <div className="pointer-events-none absolute top-3 left-3 flex items-center gap-1.5">
                        <span className="rounded-lg bg-[#FFD400] px-2.5 py-1 text-xs font-black text-black shadow">
                          #{clip.rank_order} · {clip.final_score.toFixed(0)}/100
                        </span>
                        {clip.drive_salidas && (
                          <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/90 px-2 py-1 text-[11px] font-bold text-black">
                            <CheckCircle2 className="h-3 w-3" /> En Salidas/
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="space-y-2.5 p-4">
                      <div className="text-xs font-bold uppercase tracking-wide text-[#FFD400]">
                        {clip.overlay_title}
                      </div>
                      <h3 className="text-sm font-bold leading-snug text-white">{clip.post_title}</h3>
                      <p className="text-xs text-zinc-400">{clip.reason}</p>

                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {clip.hashtags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-zinc-900 px-2 py-0.5 font-mono text-[11px] text-[#39FF14]"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>

                      <div className="flex items-center justify-between border-t border-zinc-800/80 pt-2 text-[11px] text-zinc-500">
                        <span>
                          Tramo original: {clip.start.toFixed(1)}s – {clip.end.toFixed(1)}s (
                          {clip.curated?.start_id}..{clip.curated?.end_id})
                        </span>
                        <span>
                          LLM {clip.llm_score.toFixed(0)} · Señal {(clip.signal_score * 100).toFixed(0)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 border-t border-zinc-800 bg-zinc-950/60 p-3">
                    <Link
                      href={`/editor/${clip.id}`}
                      className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-[#FFD400] px-3 py-2 text-xs font-extrabold text-black transition hover:bg-amber-300"
                    >
                      <Scissors className="h-3.5 w-3.5" /> Abrir Editor Instantáneo
                    </Link>
                    {clip.has_final && (
                      <a
                        href={`${API_PREFIX}/clips/${clip.id}/file?quality=final&download=true`}
                        className="inline-flex items-center justify-center rounded-xl border border-zinc-700 bg-zinc-900 p-2 text-zinc-200 hover:bg-zinc-800"
                        title="Descargar MP4 1080p"
                      >
                        <Download className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
