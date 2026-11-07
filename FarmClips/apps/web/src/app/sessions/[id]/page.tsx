"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Activity, ArrowLeft, CheckCircle2, Download, Flame, RefreshCw, Scissors, Sparkles, StopCircle, Wrench } from "lucide-react";
import {
  API_PREFIX,
  cancelSession,
  exportSessionToResolve,
  fetchSessionClips,
  fetchSessionDetail,
  fetchSessionSignals,
  rerunSession,
  updateManualSync,
  useServerEvents,
  type ClipItem,
  type ResolveSessionExportResponse,
  type SessionSummary,
  type SignalSeries,
} from "@/lib/api/client";
import { StepProgress } from "@/components/StepProgress";
import { PIPELINE_STEPS, friendlyState, sessionSteps } from "@/lib/pipelineSteps";
import {
  Badge,
  DetailList,
  Disclosure,
  GlassCard,
  InfoTip,
  ProgressBar,
  SoftSpinner,
  btnPrimary,
  btnSecondary,
  inputBase,
} from "@/components/ui";

const SYNC_LABEL: Record<string, string> = { audio_xcorr: "Automática por sonido", manual: "Ajustada a mano", zero: "Sin desfase" };

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
  const [exportingResolve, setExportingResolve] = useState(false);
  const [resolveSessionResult, setResolveSessionResult] = useState<ResolveSessionExportResponse | null>(null);
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

  async function handleExportSessionToResolve() {
    if (!sessionId) return;
    setExportingResolve(true);
    setError(null);
    try {
      const res = await exportSessionToResolve(sessionId, { open_in_resolve: true });
      setResolveSessionResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExportingResolve(false);
    }
  }

  if (!session) {
    return (
      <div className="space-y-6">
        {error ? (
          <GlassCard className="p-8 text-center text-sm font-semibold text-rose-200">{error}</GlassCard>
        ) : (
          <>
            <div className="h-64 animate-pulse rounded-3xl bg-slate-800/40 motion-reduce:animate-none" />
            <div className="h-44 animate-pulse rounded-3xl bg-slate-800/30 motion-reduce:animate-none" />
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
  else if (delivered) headline = `${clips.length} ${clips.length === 1 ? "clip listo para ti" : "clips listos para ti"}`;
  else if (session.state === "FAILED") headline = "El proceso se detuvo";
  else if (session.state === "CANCELLED") headline = "Sesión cancelada";
  const detail = isRunning
    ? liveStatus || PIPELINE_STEPS[steps.current].hint
    : delivered
      ? "Puedes personalizarlos en el editor rápido, descargarlos o enviarlos a DaVinci Resolve."
      : "";

  return (
    <div className="space-y-8">
      <Link
        href="/sessions"
        className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-slate-400 transition-all duration-300 hover:bg-white/5 hover:text-slate-100"
      >
        <ArrowLeft className="h-4 w-4" /> Volver a tus sesiones
      </Link>

      {/* Hero: status, 7-step track and actions --------------------------- */}
      <GlassCard as="section" className="space-y-8 p-6 sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {session.detected_game && (
                <Badge tone="info">
                  {session.detected_game.toUpperCase()}
                  <span className="font-semibold opacity-80">· Vocabulario del juego activo</span>
                </Badge>
              )}
              {session.prepared && <Badge>{Math.round(session.prepared.gameplay.duration / 60)} min de partida</Badge>}
            </div>
            <h1 className="truncate text-2xl font-black tracking-tight text-slate-50 sm:text-3xl">{session.title}</h1>
            <div className="flex items-start gap-3">
              {isRunning && <SoftSpinner className="mt-1 h-5 w-5 shrink-0" />}
              <div className="min-w-0">
                <p className="text-lg font-extrabold text-amber-300">{headline}</p>
                {detail && <p className="truncate text-sm text-slate-400">{detail}</p>}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {clips.length > 0 && !isRunning && (
              <button
                type="button"
                onClick={handleExportSessionToResolve}
                disabled={exportingResolve}
                className={btnSecondary}
              >
                {exportingResolve ? <SoftSpinner className="h-4 w-4" /> : <Sparkles className="h-4 w-4 text-sky-400" />}
                Abrir todos en DaVinci Resolve
              </button>
            )}
            {isRunning ? (
              <button
                type="button"
                onClick={() => cancelSession(session.id).then(reload)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-200 transition-all duration-300 ease-in-out hover:border-rose-400/50 hover:bg-rose-500/20 cursor-pointer"
              >
                <StopCircle className="h-4 w-4" /> Detener
              </button>
            ) : (
              <span className="flex items-center gap-1">
                <button type="button" onClick={() => rerunSession(session.id).then(reload)} className={btnPrimary}>
                  <RefreshCw className="h-4 w-4" /> Reprocesar gratis
                </button>
                <InfoTip label="¿Por qué es gratis?" align="end">
                  Como ya escuchamos y analizamos esta grabación una vez, guardamos los resultados en tu equipo para que
                  puedas volver a generar los clips sin gastar saldo.
                </InfoTip>
              </span>
            )}
          </div>
        </div>

        <StepProgress steps={PIPELINE_STEPS} statuses={steps.statuses} fill={steps.fill} current={steps.current} />

        {resolveSessionResult && (
          <div className="rounded-2xl border border-sky-400/30 bg-sky-500/10 px-4 py-3 text-xs text-sky-100">
            <span className="font-bold text-sky-300">Listo en DaVinci Resolve:</span> Se enviaron{" "}
            <strong>{resolveSessionResult.exported_count}</strong> clips listos para editar en el proyecto{" "}
            <strong className="font-mono text-white">{resolveSessionResult.project_name}</strong>.
          </div>
        )}
        {error && <p className="rounded-2xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-200">{error}</p>}
        {session.error && (
          <p className="rounded-2xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-200">Qué ocurrió: {session.error}</p>
        )}
      </GlassCard>

      {/* Excitement curve ------------------------------------------------- */}
      <GlassCard as="section" className="space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-50">
              <Activity className="h-5 w-5 text-amber-300" /> Mapa de emoción de tu partida
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
            <span className="text-sm text-slate-400">
              {signals.peaks.length} momentos intensos · {Math.round(signals.duration / 60)} min
            </span>
          )}
        </div>

        {signals && signals.excitement.length > 1 ? (
          <>
            <svg viewBox="0 0 800 130" className="h-36 w-full overflow-visible rounded-2xl bg-slate-950/60 p-2">
              {clips.map((c) => {
                const x0 = (c.start / Math.max(1, signals.duration)) * 800;
                const w = ((c.end - c.start) / Math.max(1, signals.duration)) * 800;
                return <rect key={c.id} x={x0} y={0} width={Math.max(4, w)} height={130} rx={4} fill="rgba(251, 191, 36, 0.12)" stroke="rgba(251, 191, 36, 0.35)" />;
              })}
              <polyline fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinejoin="round" points={polyline(signals.excitement)} />
              <polyline fill="none" stroke="#a78bfa" strokeWidth="1.3" strokeDasharray="3,3" points={polyline(signals.reaction)} />
              {signals.hud_activity && signals.hud_activity.length > 1 && (
                <polyline fill="none" stroke="#38bdf8" strokeWidth="1.3" opacity="0.7" points={polyline(signals.hud_activity)} />
              )}
            </svg>
            <div className="flex flex-wrap items-center gap-5 text-xs font-semibold text-slate-400">
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
          <div className="flex h-36 items-center justify-center gap-3 rounded-2xl bg-slate-950/40 text-sm text-slate-400">
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

      {/* Clips ------------------------------------------------------------ */}
      <section className="space-y-5">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-black text-slate-50">
            <Flame className="h-5 w-5 text-amber-300" /> Mejores momentos seleccionados ({clips.length})
          </h2>
          <p className="text-sm text-slate-400">
            Ordenados del más viral al más tranquilo, con la explicación de por qué funcionan para Shorts.
          </p>
        </div>

        {clips.length === 0 ? (
          <GlassCard className="flex flex-col items-center gap-3 p-12 text-center text-sm text-slate-400">
            {isRunning ? (
              <>
                <SoftSpinner className="h-6 w-6" />
                Seleccionando las mejores jugadas y reacciones…
              </>
            ) : (
              "No se encontraron momentos destacados en esta grabación."
            )}
          </GlassCard>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            {clips.map((clip) => {
              const prog = renderProgress[clip.id];
              const videoUrl = clip.has_final
                ? `${API_PREFIX}/clips/${clip.id}/file?quality=final&t=${Math.floor(clip.updated_at)}`
                : clip.has_draft
                  ? `${API_PREFIX}/clips/${clip.id}/file?quality=draft&t=${Math.floor(clip.updated_at)}`
                  : null;
              const score = Math.round(clip.final_score);

              return (
                <GlassCard key={clip.id} as="article" interactive className="flex flex-col overflow-hidden">
                  <div className="relative aspect-[9/16] max-h-[440px] w-full bg-slate-950">
                    {videoUrl ? (
                      <video src={videoUrl} controls preload="metadata" className="h-full w-full object-contain" />
                    ) : (
                      <div className="flex h-full flex-col items-center justify-center gap-4 bg-slate-800/40 p-8 text-center animate-pulse motion-reduce:animate-none">
                        <SoftSpinner className="h-8 w-8" />
                        <span className="text-sm font-bold text-slate-300">
                          {typeof prog === "number" ? "Creando video vertical…" : "Listo para editar en vivo"}
                        </span>
                        {typeof prog === "number" && (
                          <div className="w-full max-w-[12rem] space-y-1.5">
                            <ProgressBar value={prog} />
                            <span className="text-xs font-bold text-amber-300">{Math.round(prog * 100)}%</span>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="pointer-events-none absolute top-3 left-3 flex items-center gap-1.5">
                      <span className="rounded-full bg-amber-400 px-3 py-1 text-xs font-black text-slate-950 shadow-lg shadow-amber-500/30">
                        Top #{clip.rank_order} · {score} pts
                      </span>
                      {clip.drive_salidas && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/90 px-2.5 py-1 text-[11px] font-bold text-slate-950">
                          <CheckCircle2 className="h-3 w-3" /> Listo
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-1 flex-col gap-3 p-5">
                    <p className="text-xs font-bold text-slate-400">
                      Título en el video: <span className="text-slate-200">{clip.overlay_title}</span>
                    </p>
                    <h3 className="text-base font-extrabold leading-snug text-slate-50">{clip.post_title}</h3>
                    <p className="line-clamp-2 text-sm leading-relaxed text-slate-400">
                      <strong className="text-slate-300">Por qué destaca:</strong> {clip.reason}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {clip.hashtags.map((tag) => (
                        <span key={tag} className="rounded-full bg-white/5 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
                          #{tag}
                        </span>
                      ))}
                    </div>

                    <div className="mt-auto flex items-center gap-2 pt-2">
                      <Link href={`/editor/${clip.id}`} className={`${btnPrimary} flex-1`}>
                        <Scissors className="h-4 w-4" /> Personalizar clip
                      </Link>
                      {clip.has_final && (
                        <a
                          href={`${API_PREFIX}/clips/${clip.id}/file?quality=final&download=true`}
                          className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-200 transition-all duration-300 hover:scale-105 hover:bg-white/10"
                          title="Descargar video MP4"
                          aria-label="Descargar video MP4"
                        >
                          <Download className="h-4 w-4" />
                        </a>
                      )}
                      <InfoTip label="¿Cómo se calculó su nota?" align="end">
                        Ocurre del segundo {clip.start.toFixed(1)} al {clip.end.toFixed(1)}.
                        <br />
                        Historia: {clip.llm_score.toFixed(0)}/100 · Emoción en vivo: {(clip.signal_score * 100).toFixed(0)}/100 · Nota final: {score}/100.
                      </InfoTip>
                    </div>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        )}
      </section>

      {/* Technical details --------------------------------------------------- */}
      <GlassCard as="section" className="p-6">
        <Disclosure icon={<Wrench className="h-5 w-5" />} title="Sincronización de cámara y datos del archivo" subtitle="Úsalo si notas que tu voz va adelantada o atrasada respecto al juego">
          <div className="space-y-6">
            <DetailList
              items={[
                ["Código de sesión", session.id],
                ["Cómo se alineó el audio", session.sync ? SYNC_LABEL[session.sync.method] ?? session.sync.method : "Calculando…"],
                ["Ajuste de tiempo aplicado", session.sync ? `${session.sync.shift_sec.toFixed(2)} segundos` : "—"],
                ["Precisión de la alineación", session.sync ? `${Math.round(session.sync.confidence * 100)} %` : "—"],
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

            <form onSubmit={handleSaveSync} className="flex flex-wrap items-end gap-3 border-t border-white/5 pt-5">
              <label className="space-y-1.5">
                <span className="flex items-center gap-1 text-xs font-bold text-slate-400">
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
                  className={`${inputBase} w-40 font-mono`}
                />
              </label>
              <button type="submit" disabled={savingSync} className={btnSecondary}>
                {savingSync ? <SoftSpinner className="h-4 w-4" /> : null}
                Guardar ajuste y actualizar clips
              </button>
            </form>
          </div>
        </Disclosure>
      </GlassCard>
    </div>
  );
}
