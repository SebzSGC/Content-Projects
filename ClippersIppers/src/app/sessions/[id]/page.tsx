"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Wand2, Save, Timer, Download, Film, ScanFace, Wrench, Settings2, RotateCcw, CheckCircle2 } from "lucide-react";
import type { Candidate, CaptionMode, NormRect, RenderedClip, SessionSummary, WorkerJob } from "@/types/gaming";
import { worker, formatClock, waitForJob } from "@/lib/workerClient";
import { computeSteps, STEPS, stepIndexForStage } from "@/lib/gamingSteps";
import { JobProgress } from "@/components/gaming/JobProgress";
import { RegionPicker } from "@/components/gaming/RegionPicker";
import { StepProgress } from "@/components/gaming/StepProgress";
import { CandidateCard, CandidateEdits } from "@/components/gaming/CandidateCard";
import {
  Badge,
  DetailList,
  Disclosure,
  GlassCard,
  InfoTip,
  Segmented,
  SoftSpinner,
  Toggle,
  btnPrimary,
  btnSecondary,
  inputBase,
} from "@/components/gaming/ui";

type RegionKey = "camera" | "gameplay" | "subtitles";

const REGIONS: Record<RegionKey, { label: string; color: string }> = {
  camera: { label: "Cámara", color: "#A78BFA" },
  gameplay: { label: "Juego", color: "#34D399" },
  subtitles: { label: "Diálogos del juego", color: "#38BDF8" },
};

// The subtitle region is stored relative to the gameplay crop; the picker works on the full frame.
const toInner = (outer: NormRect, r: NormRect): NormRect => ({
  x: Math.max(0, (r.x - outer.x) / outer.w),
  y: Math.max(0, (r.y - outer.y) / outer.h),
  w: Math.min(1, r.w / outer.w),
  h: Math.min(1, r.h / outer.h),
});
const toOuter = (outer: NormRect, r: NormRect): NormRect => ({
  x: outer.x + r.x * outer.w,
  y: outer.y + r.y * outer.h,
  w: r.w * outer.w,
  h: r.h * outer.h,
});
const FULL: NormRect = { x: 0, y: 0, w: 1, h: 1 };

const SYNC_LABEL: Record<string, string> = {
  audio_xcorr: "por audio",
  lipsync: "por labios",
  manual: "manual",
  composite: "no aplica (video único)",
  none: "no encontrada",
};

export default function GamingSessionPage() {
  const { id } = useParams<{ id: string }>();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [clips, setClips] = useState<RenderedClip[]>([]);
  const [renderJobs, setRenderJobs] = useState<Record<string, WorkerJob>>({});
  const [health, setHealth] = useState<{ llm_provider: string; llm_model: string } | null>(null);

  // Source setup
  const [setupOpen, setSetupOpen] = useState(false);
  const [frameT, setFrameT] = useState(60);
  const [active, setActive] = useState<RegionKey>("camera");
  const [regions, setRegions] = useState<Record<RegionKey, NormRect | null>>({ camera: null, gameplay: null, subtitles: null });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [manualShift, setManualShift] = useState("");

  // Render options
  const [captions, setCaptions] = useState<CaptionMode>("streamer");
  const [titleSeconds, setTitleSeconds] = useState(25);
  const [punchIn, setPunchIn] = useState(true);
  const [voiceBoost, setVoiceBoost] = useState(true);

  const lastDone = useRef<string>("");

  const load = useCallback(async () => {
    try {
      const s = await worker.getSession(id);
      setSummary(s);
      setError(null);
      const doneKey = s.jobs.filter((j) => j.status === "done").map((j) => j.id).join(",");
      if (doneKey !== lastDone.current) {
        lastDone.current = doneKey;
        if (s.has_candidates) setCandidates(await worker.candidates(id));
        setClips(await worker.clips(id));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la sesión");
    }
  }, [id]);

  useEffect(() => {
    load();
    worker.health().then(setHealth).catch(() => setHealth(null));
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  // Initialize the picker from the saved session once.
  const initialized = useRef(false);
  useEffect(() => {
    if (!summary || initialized.current) return;
    initialized.current = true;
    const { layout, game_subtitles_region, mode } = summary.session;
    const gameOuter = mode === "composite" ? layout?.gameplay ?? null : FULL;
    setRegions({
      camera: layout?.camera ?? null,
      gameplay: layout?.gameplay ?? null,
      subtitles: game_subtitles_region && gameOuter ? toOuter(gameOuter, game_subtitles_region) : null,
    });
    setActive(mode === "split" ? "subtitles" : "camera");
    setSetupOpen(mode === "composite" && !layout);
    const duration = summary.source.gameplay?.duration;
    if (duration) setFrameT(Math.min(60, Math.floor(duration / 2)));
  }, [summary]);

  const session = summary?.session;
  const isComposite = session?.mode === "composite";
  const ingestReady = Boolean(summary?.source.gameplay);
  const pipelineJob = summary?.jobs.find((j) => (j.kind === "ingest" || j.kind === "analyze") && (j.status === "running" || j.status === "queued"));
  const lastPipeline = summary?.jobs.find((j) => j.kind === "analyze" || j.kind === "ingest");
  const duration = summary?.source.gameplay?.duration ?? summary?.manifest?.gameplay.duration ?? 0;
  const activeRenders = Object.values(renderJobs).filter((j) => j.status === "queued" || j.status === "running");
  const steps = useMemo(() => (summary ? computeSteps(summary, Object.values(renderJobs)) : null), [summary, renderJobs]);

  const pickerRegions = useMemo(
    () =>
      (isComposite ? (["camera", "gameplay", "subtitles"] as RegionKey[]) : (["subtitles"] as RegionKey[])).map((key) => ({
        key,
        label: REGIONS[key].label,
        color: REGIONS[key].color,
        rect: regions[key],
      })),
    [isComposite, regions]
  );

  const saveSetup = async () => {
    if (!session) return;
    setSaving(true);
    try {
      const gameOuter = isComposite ? regions.gameplay : FULL;
      await worker.updateSession(id, {
        ...(isComposite && regions.camera && regions.gameplay ? { layout: { camera: regions.camera, gameplay: regions.gameplay } } : {}),
        ...(regions.subtitles && gameOuter
          ? { game_subtitles_region: toInner(gameOuter, regions.subtitles) }
          : { clear_game_subtitles_region: true }),
      });
      await load();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  const analyze = async (force: boolean) => {
    try {
      await worker.analyze(id, force);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar el análisis");
    }
  };

  const saveShift = async () => {
    const value = Number(manualShift);
    if (!manualShift.trim() || !Number.isFinite(value)) return;
    try {
      await worker.setSync(id, value);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo fijar la sincronía");
    }
  };

  const render = async (candidate: Candidate, edits: CandidateEdits) => {
    try {
      const job = await worker.render(id, {
        candidate_id: candidate.id,
        start: edits.start,
        end: edits.end,
        overlay_title: edits.overlay_title,
        captions,
        title_duration_sec: titleSeconds,
        camera_ratio: 0.4,
        gameplay_focus_x: 0.5,
        punch_in: punchIn,
        voice_boost: voiceBoost,
      });
      setRenderJobs((prev) => ({ ...prev, [candidate.id]: job }));
      const final = await waitForJob(job.id, (j) => setRenderJobs((prev) => ({ ...prev, [candidate.id]: j })));
      if (final.status === "done") setClips(await worker.clips(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo renderizar");
    }
  };

  if (!summary || !session || !steps) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6 lg:px-8">
        {error ? (
          <GlassCard className="p-8 text-center text-sm text-rose-200">{error}</GlassCard>
        ) : (
          <>
            <div className="h-56 animate-pulse rounded-3xl bg-slate-800/40 motion-reduce:animate-none" />
            <div className="h-40 animate-pulse rounded-3xl bg-slate-800/30 motion-reduce:animate-none" />
          </>
        )}
      </div>
    );
  }

  const needsLayout = isComposite && !session.layout;
  const canAnalyze = ingestReady && !needsLayout && !pipelineJob;
  const sync = summary.sync;

  // Hero status: one sentence about where the session is and what to do next.
  let headline = "Listo para buscar clips";
  let detail = "Analizaremos el stream y te propondremos los mejores momentos.";
  if (pipelineJob) {
    const step = pipelineJob.kind === "ingest" ? 0 : stepIndexForStage(pipelineJob.stage);
    headline = pipelineJob.kind === "ingest" ? "Preparando la fuente" : `Analizando: ${STEPS[step].label.toLowerCase()}`;
    detail = STEPS[step].hint;
  } else if (!ingestReady) {
    headline = lastPipeline?.status === "error" ? "No pudimos leer la fuente" : "Leyendo la fuente";
    detail = session.kick_url ? "Descargando el VOD de Kick." : "Revisando los archivos.";
  } else if (needsLayout) {
    headline = "Marca la cámara y el juego";
    detail = "Dibuja dos recuadros sobre un fotograma para saber qué va arriba y qué abajo.";
  } else if (lastPipeline?.status === "error" && !summary.has_candidates) {
    headline = "El análisis se detuvo";
    detail = "Puedes reintentarlo; retomará desde el último paso completado.";
  } else if (summary.has_candidates) {
    headline = clips.length ? `${clips.length} ${clips.length === 1 ? "Short listo" : "Shorts listos"}` : `${candidates.length} momentos encontrados`;
    detail = clips.length ? "Descárgalos abajo o crea más desde los candidatos." : "Elige los que te gusten y crea tus Shorts.";
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6 lg:px-8">
      <Link href="/sessions" className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-slate-400 transition-all duration-300 hover:bg-white/5 hover:text-slate-100">
        <ArrowLeft className="h-4 w-4" /> Sesiones
      </Link>

      {/* Hero: status, 7-step track and the main action --------------------- */}
      <GlassCard as="section" className="space-y-8 p-6 sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{isComposite ? (session.kick_url ? "Kick" : "Stream completo") : "Cámara + juego"}</Badge>
              {duration > 0 && <Badge>{formatClock(duration)}</Badge>}
            </div>
            <h1 className="truncate text-2xl font-black tracking-tight text-slate-50 sm:text-3xl">
              {session.title || session.kick_url || session.gameplay_path?.split(/[\\/]/).pop()}
            </h1>
            <div className="flex items-start gap-3">
              {pipelineJob && <SoftSpinner className="mt-1 h-5 w-5 shrink-0" />}
              <div>
                <p className="text-lg font-extrabold text-amber-300">{headline}</p>
                <p className="text-sm text-slate-400">{detail}</p>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {needsLayout ? (
              <button onClick={() => setSetupOpen(true)} disabled={!ingestReady} className={btnPrimary}>
                <ScanFace className="h-4 w-4" /> Marcar cámara y juego
              </button>
            ) : (
              <button onClick={() => analyze(false)} disabled={!canAnalyze} className={btnPrimary}>
                <Wand2 className="h-4 w-4" />
                {lastPipeline?.status === "error" ? "Reintentar" : summary.has_candidates ? "Buscar de nuevo" : "Buscar clips"}
              </button>
            )}
          </div>
        </div>

        <StepProgress state={steps} />

        {pipelineJob && pipelineJob.kind === "analyze" && <JobProgress job={pipelineJob} />}
        {!pipelineJob && lastPipeline?.status === "error" && !summary.has_candidates && <JobProgress job={lastPipeline} />}
        {error && <p className="rounded-2xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-200">{error}</p>}
      </GlassCard>

      {/* Source setup (collapsed once done) ---------------------------------- */}
      <GlassCard as="section" className="p-6">
        <Disclosure
          open={setupOpen}
          onToggle={setSetupOpen}
          icon={<ScanFace className="h-5 w-5" />}
          title={isComposite ? "Cámara y juego en el video" : "Diálogos del juego (opcional)"}
          subtitle={
            isComposite
              ? session.layout
                ? "Marcados ✓ · ábrelo para ajustarlos"
                : "Pendiente: marca dónde está cada uno"
              : session.game_subtitles_region
                ? "Zona marcada ✓"
                : "Si el juego muestra sus diálogos como texto, marcarlos ayuda a saber quién habla"
          }
        >
          {!ingestReady ? (
            <div className="flex items-center gap-3 text-sm text-slate-400">
              <SoftSpinner className="h-4 w-4" />
              {session.kick_url ? "Descargando el VOD para mostrar fotogramas…" : "Leyendo la fuente…"}
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                {pickerRegions.map((r) => (
                  <button
                    key={r.key}
                    onClick={() => setActive(r.key)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold transition-all duration-300 cursor-pointer ${
                      active === r.key ? "text-slate-950 shadow-lg" : "border-white/10 bg-white/5 text-slate-400 hover:text-slate-100"
                    }`}
                    style={active === r.key ? { backgroundColor: r.color, borderColor: r.color } : undefined}
                  >
                    {r.label}
                    {r.rect && <CheckCircle2 className="h-3.5 w-3.5" />}
                  </button>
                ))}
              </div>
              <p className="text-sm text-slate-400">Elige un recuadro y arrástralo sobre el fotograma.</p>
              <div className={`grid gap-4 ${isComposite ? "" : "lg:grid-cols-[2fr_1fr]"}`}>
                <RegionPicker
                  imageUrl={worker.frameUrl(id, "gameplay", frameT)}
                  regions={pickerRegions}
                  activeKey={active}
                  onChange={(key, rect) => setRegions((prev) => ({ ...prev, [key as RegionKey]: rect }))}
                />
                {!isComposite && summary.source.camera && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={worker.frameUrl(id, "camera", frameT)} alt="Fotograma de la cámara" className="w-full rounded-2xl border border-white/10" />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <label className="flex min-w-[220px] flex-1 items-center gap-3 text-sm text-slate-400">
                  <Timer className="h-4 w-4 shrink-0" />
                  <input
                    type="range"
                    min={0}
                    max={Math.max(1, Math.floor(duration))}
                    value={frameT}
                    onChange={(e) => setFrameT(Number(e.target.value))}
                    className="flex-1 accent-amber-400"
                    aria-label="Momento del fotograma"
                  />
                  <span className="w-16 text-right font-mono text-xs">{formatClock(frameT)}</span>
                </label>
                <button onClick={saveSetup} disabled={saving || (isComposite && (!regions.camera || !regions.gameplay))} className={btnPrimary}>
                  {saving ? <SoftSpinner onAccent className="h-4 w-4" /> : saved ? <CheckCircle2 className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                  {saved ? "Guardado" : "Guardar"}
                </button>
              </div>
              {!isComposite && (
                <p className="flex items-center gap-1 text-sm text-slate-400">
                  {sync && sync.method !== "none" ? "Cámara y juego sincronizados" : "La sincronía se calcula al analizar"}
                  <InfoTip>
                    Alineamos el video de tu cámara con el del juego para que los labios coincidan con el audio. Si notas desfase, ajústalo en Detalles técnicos.
                  </InfoTip>
                </p>
              )}
            </div>
          )}
        </Disclosure>
      </GlassCard>

      {/* Candidates --------------------------------------------------------- */}
      {candidates.length > 0 && (
        <section className="space-y-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-xl font-black text-slate-50">Momentos encontrados</h2>
              <p className="text-sm text-slate-400">Ordenados del más prometedor al menos.</p>
            </div>
          </div>

          <GlassCard className="p-5">
            <Disclosure
              icon={<Settings2 className="h-5 w-5" />}
              title="Opciones del Short"
              subtitle={`Subtítulos: ${captions === "streamer" ? "solo streamer" : captions === "all" ? "streamer + juego" : "sin subtítulos"} · título ${titleSeconds} s${punchIn ? " · zoom en la reacción" : ""}`}
            >
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2">
                  <span className="text-sm font-bold text-slate-200">Subtítulos</span>
                  <Segmented
                    className="w-full"
                    value={captions}
                    onChange={setCaptions}
                    options={[
                      { value: "streamer", label: "Solo streamer" },
                      { value: "all", label: "+ juego" },
                      { value: "none", label: "Sin" },
                    ]}
                  />
                </div>
                <label className="block space-y-2">
                  <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
                    Título en pantalla durante
                    <InfoTip>Segundos que el título queda en la unión entre cámara y juego. 0 lo oculta.</InfoTip>
                  </span>
                  <div className="flex items-center gap-2">
                    <input type="number" min={0} max={120} value={titleSeconds} onChange={(e) => setTitleSeconds(Number(e.target.value))} className={`${inputBase} w-24 font-mono`} />
                    <span className="text-sm text-slate-400">segundos</span>
                  </div>
                </label>
                <Toggle checked={punchIn} onChange={setPunchIn} label="Zoom a la cara en la reacción" />
                <Toggle checked={voiceBoost} onChange={setVoiceBoost} label="Realzar la voz" />
              </div>
            </Disclosure>
          </GlassCard>

          <div className="grid gap-5 lg:grid-cols-2">
            {candidates.map((c, i) => (
              <CandidateCard key={c.id} candidate={c} rank={i + 1} job={renderJobs[c.id]} onRender={(edits) => render(c, edits)} />
            ))}
          </div>
        </section>
      )}

      {/* Rendered Shorts ---------------------------------------------------- */}
      {(clips.length > 0 || activeRenders.length > 0) && (
        <section className="space-y-5">
          <h2 className="flex items-center gap-2 text-xl font-black text-slate-50">
            <Film className="h-5 w-5 text-amber-300" /> Tus Shorts
          </h2>
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
            {activeRenders.map((job) => (
              <div key={job.id} className="space-y-3 rounded-3xl border border-white/[0.06] bg-slate-800/40 p-3">
                <div className="relative flex aspect-[9/16] items-center justify-center overflow-hidden rounded-2xl bg-slate-700/30 animate-pulse motion-reduce:animate-none">
                  <SoftSpinner className="h-8 w-8" />
                </div>
                <p className="px-1 text-xs font-bold text-slate-400">Creando… {Math.round(job.progress * 100)}%</p>
              </div>
            ))}
            {[...clips].reverse().map((clip) => (
              <GlassCard key={clip.id} interactive className="space-y-3 p-3">
                <video src={worker.clipUrl(id, clip.id)} controls preload="metadata" className="aspect-[9/16] w-full rounded-2xl bg-black object-cover" />
                <div className="flex items-center justify-between gap-2 px-1">
                  <p className="truncate text-sm font-bold text-slate-200">{clip.overlay_title}</p>
                  <a
                    href={worker.clipUrl(id, clip.id, true)}
                    className="shrink-0 rounded-full bg-amber-400 p-2 text-slate-950 shadow-md shadow-amber-500/20 transition-all duration-300 hover:scale-110 hover:bg-amber-300"
                    title="Descargar"
                    aria-label={`Descargar ${clip.overlay_title}`}
                  >
                    <Download className="h-4 w-4" />
                  </a>
                </div>
              </GlassCard>
            ))}
          </div>
        </section>
      )}

      {/* Technical details (progressive disclosure) -------------------------- */}
      <GlassCard as="section" className="p-6">
        <Disclosure icon={<Wrench className="h-5 w-5" />} title="Detalles técnicos" subtitle="Archivos, resolución, sincronía y modelo de IA">
          <div className="space-y-6">
            <DetailList
              items={[
                ["Sesión", session.id],
                ["Idioma", session.language || "auto"],
                ["Huella de voz", session.voiceprint || "—"],
                ["IA", health ? `${health.llm_provider} · ${health.llm_model}` : "—"],
                ["Video del juego", summary.source.gameplay?.path ?? session.gameplay_path ?? session.kick_url ?? "—"],
                [
                  "Juego",
                  summary.source.gameplay
                    ? `${summary.source.gameplay.width}×${summary.source.gameplay.height} · ${summary.source.gameplay.fps} fps · audio ${summary.source.gameplay.has_audio ? "sí" : "no"}`
                    : "—",
                ],
                ...(!isComposite
                  ? ([
                      ["Video de la cámara", summary.source.camera?.path ?? session.camera_path ?? "—"],
                      [
                        "Cámara",
                        summary.source.camera
                          ? `${summary.source.camera.width}×${summary.source.camera.height} · ${summary.source.camera.fps} fps · audio ${summary.source.camera.has_audio ? "sí" : "no"}`
                          : "—",
                      ],
                    ] as Array<[string, React.ReactNode]>)
                  : []),
                ["Proxies de análisis", summary.manifest ? `${summary.manifest.proxy_fps} fps · audio mono 16 kHz` : "—"],
                [
                  "Sincronía",
                  sync
                    ? `${SYNC_LABEL[sync.method] ?? sync.method} · desfase ${sync.shift_sec.toFixed(3)} s · escala ${sync.scale.toFixed(6)} · confianza ${Math.round(sync.confidence * 100)} %`
                    : "—",
                ],
              ]}
            />

            {!isComposite && (
              <div className="flex flex-wrap items-end gap-3 border-t border-white/5 pt-5">
                <label className="space-y-1.5">
                  <span className="flex items-center gap-1 text-xs font-bold text-slate-400">
                    Desfase manual (s)
                    <InfoTip>Positivo si la cámara empezó a grabar antes que el juego. Tiene prioridad sobre el cálculo automático.</InfoTip>
                  </span>
                  <input value={manualShift} onChange={(e) => setManualShift(e.target.value)} placeholder="0.000" className={`${inputBase} w-36 font-mono`} />
                </label>
                <button onClick={saveShift} className={btnSecondary}>
                  Fijar desfase
                </button>
              </div>
            )}

            {summary.has_candidates && (
              <div className="flex flex-wrap items-center gap-3 border-t border-white/5 pt-5">
                <button onClick={() => analyze(true)} disabled={!canAnalyze} className={btnSecondary}>
                  <RotateCcw className="h-4 w-4" /> Reanalizar desde cero
                </button>
                <span className="text-xs text-slate-500">Repite todas las etapas aunque ya tengan resultados.</span>
              </div>
            )}
          </div>
        </Disclosure>
      </GlassCard>
    </div>
  );
}
