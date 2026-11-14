"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  Check,
  CheckCircle2,
  Copy,
  Download,
  Flame,
  FolderOpen,
  Layers,
  RefreshCw,
  Scissors,
  StopCircle,
  Wrench,
} from "lucide-react";
import {
  API_PREFIX,
  cancelSession,
  fetchSessionClips,
  fetchSessionDetail,
  fetchSessionSignals,
  getSessionFilmCraftDownloadUrl,
  openSessionInFilmCraft,
  rerunSession,
  revealSessionFilmCraftProject,
  updateManualSync,
  useServerEvents,
  type ClipItem,
  type SessionSummary,
  type SignalSeries,
} from "@/lib/api/client";
import { StepProgress } from "@/components/StepProgress";
import { PIPELINE_STEPS, friendlyState, sessionSteps } from "@/lib/pipelineSteps";
import {
  Badge,
  DetailList,
  Disclosure,
  EmptyState,
  GlassCard,
  InfoTip,
  ProgressBar,
  SoftSpinner,
  btnDanger,
  btnGhost,
  btnPrimary,
  btnSecondary,
  inputBase,
} from "@/components/ui";

const SYNC_LABEL: Record<string, string> = {
  audio_xcorr: "Automática por sonido",
  manual: "Ajustada a mano",
  zero: "Sin desfase",
};

function polyline(values: number[]): string {
  return values
    .map((v, idx) => {
      const x = (idx / Math.max(1, values.length - 1)) * 800;
      const y = 122 - v * 110;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
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
  const [targetClips, setTargetClips] = useState<number>(5);
  const [error, setError] = useState<string | null>(null);
  const [selectedClipIds, setSelectedClipIds] = useState<Set<string>>(new Set());
  const selectionInitRef = useRef(false);
  const [openingFilmCraft, setOpeningFilmCraft] = useState(false);
  const [filmcraftMsg, setFilmcraftMsg] = useState<string>("");
  const [filmcraftProjectPath, setFilmcraftProjectPath] = useState<string>("");
  const [copiedFcPath, setCopiedFcPath] = useState(false);

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
      if (typeof ses.max_clips === "number" && ses.max_clips >= 1) {
        setTargetClips(ses.max_clips);
      }
      if (cl.length > 0) {
        if (!selectionInitRef.current) {
          setSelectedClipIds(new Set(cl.map((c) => c.id)));
          selectionInitRef.current = true;
        } else {
          const valid = new Set(cl.map((c) => c.id));
          setSelectedClipIds((prev) => new Set([...prev].filter((id) => valid.has(id))));
        }
      }
      if (ses.sync) {
        setManualShift(ses.sync.shift_sec.toFixed(3));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId]);

  const selectedIdsList = clips.filter((c) => selectedClipIds.has(c.id)).map((c) => c.id);

  function toggleClipSelection(clipId: string) {
    setSelectedClipIds((prev) => {
      const next = new Set(prev);
      if (next.has(clipId)) next.delete(clipId);
      else next.add(clipId);
      return next;
    });
  }

  async function handleOpenSessionInFilmCraft() {
    if (!sessionId || selectedIdsList.length === 0) return;
    setOpeningFilmCraft(true);
    setError(null);
    setFilmcraftMsg("");
    try {
      const res = await openSessionInFilmCraft(sessionId, selectedIdsList);
      setFilmcraftProjectPath(res.project_path || "");
      const warns =
        res.warnings && res.warnings.length > 0 ? ` (${res.warnings.length} avisos)` : "";
      setFilmcraftMsg(
        res.reused_instance
          ? `Proyecto global (${res.clips_count} clips + VOD completo) abierto en tu ventana activa de FilmCraft${warns}.`
          : `FilmCraft iniciado con el proyecto global (${res.clips_count} clips + VOD completo)${warns}.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo abrir FilmCraft.");
    } finally {
      setOpeningFilmCraft(false);
    }
  }

  async function handleRevealSessionFilmCraft() {
    if (!sessionId || selectedIdsList.length === 0) return;
    try {
      await revealSessionFilmCraftProject(sessionId, selectedIdsList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo abrir la carpeta del proyecto.");
    }
  }

  function handleCopySessionFilmCraftPath() {
    if (!filmcraftProjectPath) return;
    navigator.clipboard.writeText(filmcraftProjectPath);
    setCopiedFcPath(true);
    setTimeout(() => setCopiedFcPath(false), 2000);
  }

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
      <div className="space-y-5">
        {error ? (
          <GlassCard className="p-8 text-center text-sm font-medium text-rose-200">
            {error}
          </GlassCard>
        ) : (
          <>
            <div className="h-56 animate-pulse rounded-xl border border-white/[0.05] bg-[#161922] motion-reduce:animate-none" />
            <div className="h-44 animate-pulse rounded-xl border border-white/[0.05] bg-[#161922] motion-reduce:animate-none" />
          </>
        )}
      </div>
    );
  }

  const steps = sessionSteps(session);
  const isRunning = steps.running;
  const delivered = session.state === "DELIVERED";

  let headline = friendlyState(session.state);
  if (isRunning) headline = `${PIPELINE_STEPS[steps.current].label}…`;
  else if (delivered)
    headline = `${clips.length} ${clips.length === 1 ? "clip listo para ti" : "clips listos para ti"}`;
  else if (session.state === "FAILED") headline = "El proceso se detuvo";
  else if (session.state === "CANCELLED") headline = "Sesión cancelada";

  const detail = isRunning
    ? liveStatus || PIPELINE_STEPS[steps.current].hint
    : delivered
      ? "Personalízalos en el editor interactivo a 60 fps, ábrelos como proyecto en FilmCraft o descárgalos en 1080p."
      : "";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/sessions" className={btnGhost}>
          <ArrowLeft className="h-3.5 w-3.5" /> Volver a tus sesiones
        </Link>
        <span className="font-mono text-[11px] text-slate-500">ID: {session.id}</span>
      </div>

      {/* Hero: Session Status, 7-Step Track and Primary Actions */}
      <GlassCard as="section" className="space-y-6 p-5 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-2.5">
            <div className="flex flex-wrap items-center gap-2">
              {session.detected_game && (
                <Badge tone="info">
                  {session.detected_game.toUpperCase()}
                  <span className="font-normal opacity-80">· Vocabulario del juego activo</span>
                </Badge>
              )}
              {session.prepared && (
                <Badge>
                  <span className="font-mono tabular-nums">
                    {Math.round(session.prepared.gameplay.duration / 60)} min
                  </span>{" "}
                  de partida
                </Badge>
              )}
              {typeof session.max_clips === "number" && (
                <Badge>
                  Objetivo:{" "}
                  <span className="font-mono tabular-nums">{session.max_clips}</span>{" "}
                  {session.max_clips === 1 ? "clip" : "clips"}
                </Badge>
              )}
            </div>
            <h1 className="truncate text-xl font-bold tracking-tight text-slate-50 sm:text-2xl">
              {session.title}
            </h1>
            <div className="flex items-start gap-2.5">
              {isRunning && <SoftSpinner className="mt-1 h-4 w-4 shrink-0" />}
              <div className="min-w-0">
                <p className="text-sm sm:text-base font-bold text-amber-300">{headline}</p>
                {detail && <p className="truncate text-xs sm:text-sm text-slate-400">{detail}</p>}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {isRunning ? (
              <button
                type="button"
                onClick={() => cancelSession(session.id).then(reload)}
                className={btnDanger}
              >
                <StopCircle className="h-4 w-4" /> Detener proceso
              </button>
            ) : (
              <span className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-[#0e1016] px-2.5 py-1.5 text-xs text-slate-300">
                  <span>Clips:</span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    step={1}
                    aria-label="Cantidad de clips a reprocesar"
                    value={targetClips}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      if (!Number.isNaN(val)) {
                        setTargetClips(Math.max(1, Math.min(20, val)));
                      }
                    }}
                    className="w-12 bg-transparent text-center font-mono text-xs font-bold text-amber-300 focus:outline-none"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => rerunSession(session.id, targetClips).then(reload)}
                  className={btnPrimary}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Reprocesar gratis
                </button>
                <InfoTip label="¿Por qué es gratis?" align="end">
                  Como ya escuchamos y analizamos esta grabación una vez, guardamos los resultados en tu equipo para que
                  puedas volver a generar los clips sin gastar saldo.
                </InfoTip>
              </span>
            )}
          </div>
        </div>

        <StepProgress
          steps={PIPELINE_STEPS}
          statuses={steps.statuses}
          fill={steps.fill}
          current={steps.current}
        />

        {error && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-xs sm:text-sm font-medium text-rose-200">
            {error}
          </p>
        )}
        {session.error && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-xs sm:text-sm font-medium text-rose-200">
            Qué ocurrió: {session.error}
          </p>
        )}
      </GlassCard>

      {/* Excitement Curve Telemetry Card */}
      <GlassCard as="section" className="space-y-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-50">
              <Activity className="h-4 w-4 text-amber-300" /> Mapa de emoción de tu partida
              <InfoTip>
                Unimos la intensidad de tu voz con la acción en pantalla para detectar dónde ocurrieron las mejores
                jugadas y reacciones. Las franjas doradas son los clips seleccionados.
              </InfoTip>
            </h2>
            <p className="text-xs text-slate-400">
              Las zonas resaltadas en dorado muestran por qué elegimos cada clip justo cuando subió la energía.
            </p>
          </div>
          {signals && (
            <div className="flex items-center gap-2 font-mono text-xs text-slate-400 tabular-nums">
              <Badge tone="gold">{signals.peaks.length} picos</Badge>
              <Badge>{Math.round(signals.duration / 60)} min</Badge>
            </div>
          )}
        </div>

        {signals && signals.excitement.length > 1 ? (
          <>
            <div className="ax-card-muted overflow-hidden p-3">
              <svg viewBox="0 0 800 130" className="h-36 w-full overflow-visible">
                {/* Subtle horizontal reference lines */}
                {[25, 62, 98].map((yLine) => (
                  <line
                    key={yLine}
                    x1={0}
                    y1={yLine}
                    x2={800}
                    y2={yLine}
                    stroke="rgba(255,255,255,0.05)"
                    strokeDasharray="2,4"
                  />
                ))}
                {clips.map((c) => {
                  const x0 = (c.start / Math.max(1, signals.duration)) * 800;
                  const w = ((c.end - c.start) / Math.max(1, signals.duration)) * 800;
                  return (
                    <rect
                      key={c.id}
                      x={x0}
                      y={2}
                      width={Math.max(4, w)}
                      height={126}
                      rx={3}
                      fill="rgba(245, 158, 11, 0.14)"
                      stroke="rgba(245, 158, 11, 0.42)"
                    />
                  );
                })}
                <polyline
                  fill="none"
                  stroke="#fbbf24"
                  strokeWidth="2"
                  strokeLinejoin="round"
                  points={polyline(signals.excitement)}
                />
                <polyline
                  fill="none"
                  stroke="#a78bfa"
                  strokeWidth="1.3"
                  strokeDasharray="3,3"
                  points={polyline(signals.reaction)}
                />
                {signals.hud_activity && signals.hud_activity.length > 1 && (
                  <polyline
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="1.3"
                    opacity="0.75"
                    points={polyline(signals.hud_activity)}
                  />
                )}
              </svg>
            </div>
            <div className="flex flex-wrap items-center gap-5 text-xs font-medium text-slate-400">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-400" /> Emoción general
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-violet-400" /> Tu voz y reacciones
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-sky-400" /> Acción en la partida
              </span>
            </div>
          </>
        ) : (
          <div className="ax-card-muted flex h-36 items-center justify-center gap-2.5 text-xs sm:text-sm text-slate-400">
            {isRunning ? (
              <>
                <SoftSpinner className="h-4 w-4" /> Buscando los momentos más intensos de la partida…
              </>
            ) : (
              "Aún no hay mapa de emoción para esta sesión."
            )}
          </div>
        )}
      </GlassCard>

      {/* Clips Gallery & FilmCraft Master Project Toolbar */}
      <section className="space-y-4">
        <div className="flex flex-col gap-3.5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold text-slate-50">
              <Flame className="h-4 w-4 text-amber-300" /> Mejores momentos seleccionados (
              <span className="font-mono tabular-nums">{clips.length}</span>)
            </h2>
            <p className="text-xs sm:text-sm text-slate-400">
              Elige los clips que quieras incluir para abrir todo el proyecto (VOD completo + sub-secuencias) en FilmCraft, o edita uno a uno.
            </p>
          </div>

          {clips.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.09] bg-[#0e1016] px-3 py-1.5 text-xs font-medium text-slate-300">
                <span className="font-mono tabular-nums">
                  {selectedIdsList.length} de {clips.length} elegidos
                </span>
                <span className="text-slate-600">·</span>
                <button
                  type="button"
                  onClick={() => setSelectedClipIds(new Set(clips.map((c) => c.id)))}
                  className="font-semibold text-amber-300 hover:text-amber-200 cursor-pointer"
                >
                  Todos
                </button>
                <span className="text-slate-600">/</span>
                <button
                  type="button"
                  onClick={() => setSelectedClipIds(new Set())}
                  className="font-semibold text-slate-400 hover:text-slate-200 cursor-pointer"
                >
                  Ninguno
                </button>
              </div>

              <button
                type="button"
                onClick={handleOpenSessionInFilmCraft}
                disabled={openingFilmCraft || selectedIdsList.length === 0}
                className="inline-flex items-center gap-2 rounded-lg border border-sky-400/35 bg-sky-500/12 px-3.5 py-2 text-xs font-semibold text-sky-300 transition-colors duration-150 hover:border-sky-400/55 hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-45 cursor-pointer"
                title="Exporta un único .fcproj con el VOD completo y sub-secuencias 9:16 para los clips seleccionados"
              >
                {openingFilmCraft ? (
                  <SoftSpinner className="h-3.5 w-3.5" />
                ) : (
                  <Layers className="h-3.5 w-3.5" />
                )}
                {openingFilmCraft
                  ? "Montando proyecto..."
                  : `Abrir proyecto en FilmCraft (${selectedIdsList.length})`}
              </button>

              {selectedIdsList.length > 0 && (
                <a
                  href={getSessionFilmCraftDownloadUrl(session.id, selectedIdsList)}
                  download={`${session.id}_master.fcproj`}
                  className={btnSecondary}
                  title="Descargar proyecto .fcproj global sin abrir FilmCraft"
                >
                  <Download className="h-3.5 w-3.5" /> .fcproj
                </a>
              )}
            </div>
          )}
        </div>

        {filmcraftMsg && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-xs sm:text-sm text-emerald-200">
            <div className="flex items-center gap-2">
              <Check className="h-4 w-4 shrink-0 text-emerald-400" />
              <span>{filmcraftMsg}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleRevealSessionFilmCraft}
                className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-950/60 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/60 cursor-pointer"
              >
                <FolderOpen className="h-3.5 w-3.5" /> Abrir carpeta
              </button>
              {filmcraftProjectPath && (
                <button
                  type="button"
                  onClick={handleCopySessionFilmCraftPath}
                  className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-950/60 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/60 cursor-pointer"
                >
                  <Copy className="h-3.5 w-3.5" /> {copiedFcPath ? "¡Copiada!" : "Copiar ruta"}
                </button>
              )}
              <button
                type="button"
                onClick={() => setFilmcraftMsg("")}
                className="text-xs text-slate-400 hover:text-white cursor-pointer"
              >
                Cerrar
              </button>
            </div>
          </div>
        )}

        {clips.length === 0 ? (
          <EmptyState
            icon={
              isRunning ? (
                <SoftSpinner className="h-5 w-5" />
              ) : (
                <Flame className="h-5 w-5 text-slate-400" />
              )
            }
            title={
              isRunning
                ? "Seleccionando las mejores jugadas y reacciones…"
                : "No se encontraron momentos destacados en esta grabación"
            }
            description={
              isRunning
                ? "El motor de IA está puntuando cada tramo según tu voz y la actividad en pantalla."
                : "Puedes volver a procesar la sesión si ajustaste los parámetros."
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {clips.map((clip) => {
              const prog = renderProgress[clip.id];
              const videoUrl = clip.has_final
                ? `${API_PREFIX}/clips/${clip.id}/file?quality=final&t=${Math.floor(clip.updated_at)}`
                : clip.has_draft
                  ? `${API_PREFIX}/clips/${clip.id}/file?quality=draft&t=${Math.floor(clip.updated_at)}`
                  : null;
              const score = Math.round(clip.final_score);
              const isSelected = selectedClipIds.has(clip.id);

              return (
                <GlassCard
                  key={clip.id}
                  as="article"
                  interactive
                  className={`flex flex-col overflow-hidden transition-all ${
                    isSelected ? "ring-1 ring-sky-400/55" : "opacity-85"
                  }`}
                >
                  <div className="group relative aspect-[9/16] max-h-[420px] w-full overflow-hidden border-b border-white/[0.06] bg-[#090b0f]">
                    {videoUrl ? (
                      <video
                        src={videoUrl}
                        controls
                        preload="metadata"
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      <div className="relative h-full w-full">
                        <img
                          src={`${API_PREFIX}/clips/${clip.id}/thumbnail?t=${Math.floor(clip.updated_at)}`}
                          alt={clip.post_title}
                          loading="lazy"
                          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                          onError={(e) => {
                            if (session) {
                              (e.currentTarget as HTMLImageElement).src = `${API_PREFIX}/sessions/${session.id}/frame?source=gameplay&t=${clip.start}&width=540`;
                            }
                          }}
                        />

                        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-black/45" />

                        {typeof prog === "number" ? (
                          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/85 p-6 text-center backdrop-blur-xs">
                            <SoftSpinner className="h-7 w-7 text-amber-400" />
                            <span className="text-xs sm:text-sm font-semibold text-slate-100">
                              Creando video vertical…
                            </span>
                            <div className="w-full max-w-[11rem] space-y-1.5">
                              <ProgressBar value={prog} />
                              <span className="font-mono text-xs font-bold text-amber-300 tabular-nums">
                                {Math.round(prog * 100)}%
                              </span>
                            </div>
                          </div>
                        ) : (
                          <div className="absolute inset-0 flex items-center justify-center p-4">
                            <Link
                              href={`/editor/${clip.id}`}
                              className="flex items-center gap-2 rounded-lg border border-amber-400/45 bg-[#0b0d11]/90 px-3.5 py-2 text-xs font-bold text-amber-300 shadow-xl backdrop-blur-md transition-colors duration-150 hover:border-amber-300 hover:bg-amber-400 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-amber-400"
                            >
                              <Scissors className="h-3.5 w-3.5" />
                              <span>Personalizar en vivo</span>
                            </Link>
                          </div>
                        )}

                        {typeof prog !== "number" && (
                          <div className="pointer-events-none absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between text-[11px] font-semibold text-slate-200">
                            <span className="rounded-md border border-white/[0.1] bg-black/70 px-2 py-0.5 backdrop-blur-xs">
                              Borrador listo
                            </span>
                            <span className="rounded-md border border-white/[0.1] bg-black/70 px-2 py-0.5 font-mono tabular-nums backdrop-blur-xs">
                              {Math.round(clip.end - clip.start)} s
                            </span>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="pointer-events-none absolute top-2.5 left-2.5 flex items-center gap-1.5">
                      <span className="rounded-md bg-amber-400 px-2.5 py-1 font-mono text-[11px] font-bold text-slate-950 shadow tabular-nums">
                        #{clip.rank_order} · {score} pts
                      </span>
                      {clip.drive_salidas && (
                        <span className="inline-flex items-center gap-1 rounded-md bg-emerald-400 px-2 py-1 text-[10px] font-bold text-slate-950">
                          <CheckCircle2 className="h-3 w-3" /> Entregado
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => toggleClipSelection(clip.id)}
                      aria-pressed={isSelected}
                      title={
                        isSelected
                          ? "Quitar clip de la exportación global a FilmCraft"
                          : "Incluir clip en la exportación global a FilmCraft"
                      }
                      className={`absolute top-2.5 right-2.5 z-10 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold backdrop-blur-md transition-colors cursor-pointer ${
                        isSelected
                          ? "border-sky-400/70 bg-sky-500/85 text-slate-950 shadow"
                          : "border-white/20 bg-black/75 text-slate-300 hover:border-white/40"
                      }`}
                    >
                      <span
                        className={`flex h-3.5 w-3.5 items-center justify-center rounded-[4px] border ${
                          isSelected
                            ? "border-slate-950 bg-slate-950 text-sky-300"
                            : "border-slate-400"
                        }`}
                      >
                        {isSelected && <Check className="h-2.5 w-2.5 stroke-[3]" />}
                      </span>
                      {isSelected ? "Incluido" : "Incluir"}
                    </button>
                  </div>

                  <div className="flex flex-1 flex-col gap-2.5 p-4 sm:p-5">
                    <div className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="truncate font-medium text-slate-400">
                        Overlay: <strong className="text-slate-200">{clip.overlay_title}</strong>
                      </span>
                      <span className="shrink-0 font-mono text-slate-500 tabular-nums">
                        {clip.start.toFixed(1)}s–{clip.end.toFixed(1)}s
                      </span>
                    </div>

                    <h3 className="text-sm sm:text-base font-bold leading-snug text-slate-50">
                      {clip.post_title}
                    </h3>

                    <p className="line-clamp-2 text-xs leading-relaxed text-slate-400">
                      <strong className="text-slate-300">Por qué destaca:</strong> {clip.reason}
                    </p>

                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {clip.hashtags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-md border border-white/[0.06] bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] text-slate-400"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>

                    <div className="mt-auto flex items-center gap-2 border-t border-white/[0.06] pt-3">
                      <Link href={`/editor/${clip.id}`} className={`${btnPrimary} flex-1`}>
                        <Scissors className="h-3.5 w-3.5" /> Personalizar clip
                      </Link>
                      {clip.has_final && (
                        <a
                          href={`${API_PREFIX}/clips/${clip.id}/file?quality=final&download=true`}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/[0.09] bg-white/[0.04] text-slate-200 transition-colors duration-150 hover:bg-white/[0.09]"
                          title="Descargar video MP4"
                          aria-label="Descargar video MP4"
                        >
                          <Download className="h-4 w-4" />
                        </a>
                      )}
                      <InfoTip label="¿Cómo se calculó su nota?" align="end">
                        Ocurre del segundo {clip.start.toFixed(1)} al {clip.end.toFixed(1)}.
                        <br />
                        Historia: {clip.llm_score.toFixed(0)}/100 · Emoción en vivo:{" "}
                        {(clip.signal_score * 100).toFixed(0)}/100 · Nota final: {score}/100.
                      </InfoTip>
                    </div>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        )}
      </section>

      {/* Technical Sync & File Metadata (Progressive Disclosure) */}
      <GlassCard as="section" className="p-5 sm:p-6">
        <Disclosure
          icon={<Wrench className="h-4 w-4" />}
          title="Sincronización de cámara y datos del archivo"
          subtitle="Úsalo si notas que tu voz va adelantada o atrasada respecto al juego"
        >
          <div className="space-y-5">
            <DetailList
              items={[
                ["Código de sesión", session.id],
                [
                  "Cómo se alineó el audio",
                  session.sync
                    ? SYNC_LABEL[session.sync.method] ?? session.sync.method
                    : "Calculando…",
                ],
                [
                  "Ajuste de tiempo aplicado",
                  session.sync ? `${session.sync.shift_sec.toFixed(2)} segundos` : "—",
                ],
                [
                  "Precisión de la alineación",
                  session.sync ? `${Math.round(session.sync.confidence * 100)} %` : "—",
                ],
                [
                  "Mezcla de sonido",
                  session.prepared
                    ? session.prepared.gameplay_clean_audio_stream != null
                      ? "Baja el volumen del juego automáticamente cuando hablas"
                      : "Realza tu voz sobre el sonido del juego"
                    : "—",
                ],
                [
                  "Calidad del video del juego",
                  session.prepared
                    ? `${session.prepared.gameplay.width}×${session.prepared.gameplay.height} a ${session.prepared.gameplay.fps} fps`
                    : "—",
                ],
                [
                  "Calidad de tu cámara",
                  session.prepared
                    ? `${session.prepared.camera.width}×${session.prepared.camera.height} a ${session.prepared.camera.fps} fps`
                    : "—",
                ],
                ["Estilo visual", session.style_preset],
              ]}
            />

            <form
              onSubmit={handleSaveSync}
              className="flex flex-wrap items-end gap-3 border-t border-white/[0.06] pt-4"
            >
              <label className="space-y-1.5">
                <span className="flex items-center gap-1 text-xs font-semibold text-slate-300">
                  Corregir desfase de la cámara (en segundos)
                  <InfoTip>
                    Si ves que tus labios se mueven antes o después de que suene el disparo, cambia este número y vuelve
                    a aplicar.
                  </InfoTip>
                </span>
                <input
                  type="number"
                  step="0.05"
                  value={manualShift}
                  onChange={(e) => setManualShift(e.target.value)}
                  className={`${inputBase} w-40 font-mono tabular-nums`}
                />
              </label>
              <button type="submit" disabled={savingSync} className={btnSecondary}>
                {savingSync ? <SoftSpinner className="h-3.5 w-3.5" /> : null}
                Guardar ajuste y actualizar clips
              </button>
            </form>
          </div>
        </Disclosure>
      </GlassCard>
    </div>
  );
}
