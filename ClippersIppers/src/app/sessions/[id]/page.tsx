"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Wand2,
  Save,
  Loader2,
  Timer,
  Settings2,
  Download,
  Film,
  ScanFace,
  AlertTriangle,
} from "lucide-react";
import type {
  Candidate,
  CaptionMode,
  NormRect,
  RenderedClip,
  SessionSummary,
  WorkerJob,
} from "@/types/gaming";
import { worker, formatClock, waitForJob } from "@/lib/workerClient";
import { JobProgress } from "@/components/gaming/JobProgress";
import { RegionPicker } from "@/components/gaming/RegionPicker";
import { CandidateCard, CandidateEdits } from "@/components/gaming/CandidateCard";

type RegionKey = "camera" | "gameplay" | "subtitles";

const COLORS: Record<RegionKey, string> = { camera: "#7652E8", gameplay: "#10B981", subtitles: "#F59E0B" };

// Subtitle region is stored relative to the gameplay crop; the picker works on the full frame.
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

export default function GamingSessionPage() {
  const { id } = useParams<{ id: string }>();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [clips, setClips] = useState<RenderedClip[]>([]);
  const [renderJobs, setRenderJobs] = useState<Record<string, WorkerJob>>({});

  // Source setup
  const [frameT, setFrameT] = useState(60);
  const [active, setActive] = useState<RegionKey>("camera");
  const [regions, setRegions] = useState<Record<RegionKey, NormRect | null>>({ camera: null, gameplay: null, subtitles: null });
  const [saving, setSaving] = useState(false);
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
    if (mode === "split") setActive("subtitles");
    const duration = summary.source.gameplay?.duration;
    if (duration) setFrameT(Math.min(60, duration / 2));
  }, [summary]);

  const session = summary?.session;
  const isComposite = session?.mode === "composite";
  const ingestReady = Boolean(summary?.source.gameplay);
  const activeJob = summary?.jobs.find((j) => (j.kind === "ingest" || j.kind === "analyze") && (j.status === "running" || j.status === "queued"));
  const lastAnalysis = summary?.jobs.find((j) => j.kind === "analyze" || j.kind === "ingest");
  const duration = summary?.source.gameplay?.duration ?? summary?.manifest?.gameplay.duration ?? 0;

  const pickerRegions = useMemo(
    () =>
      (isComposite ? (["camera", "gameplay", "subtitles"] as RegionKey[]) : (["subtitles"] as RegionKey[])).map((key) => ({
        key,
        label: key === "camera" ? "Cámara" : key === "gameplay" ? "Juego" : "Diálogos del juego",
        color: COLORS[key],
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
        ...(isComposite && regions.camera && regions.gameplay
          ? { layout: { camera: regions.camera, gameplay: regions.gameplay } }
          : {}),
        ...(regions.subtitles && gameOuter
          ? { game_subtitles_region: toInner(gameOuter, regions.subtitles) }
          : { clear_game_subtitles_region: true }),
      });
      await load();
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
    if (!Number.isFinite(value)) return;
    await worker.setSync(id, value).catch((e) => setError(e.message));
    await load();
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

  if (!summary || !session) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 text-center text-xs text-[var(--muted-foreground)]">
        {error ? error : <Loader2 className="h-5 w-5 animate-spin mx-auto" />}
      </div>
    );
  }

  const canAnalyze = ingestReady && (!isComposite || Boolean(session.layout)) && !activeJob;
  const sync = summary.sync;

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="border-b border-[var(--border)] pb-5 space-y-2">
        <Link href="/sessions" className="inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
          <ArrowLeft className="h-3.5 w-3.5" /> Sesiones
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] truncate">
              {session.title || session.kick_url || session.gameplay_path?.split(/[\\/]/).pop()}
            </h1>
            <p className="text-xs text-[var(--muted-foreground)]">
              {isComposite ? (session.kick_url ? "VOD de Kick" : "Stream compuesto") : "Cámara + juego"}
              {duration ? ` · ${formatClock(duration)}` : ""}
              {session.voiceprint ? ` · voz: ${session.voiceprint}` : ""}
            </p>
          </div>
          <div className="flex gap-2">
            {summary.has_candidates && (
              <button
                onClick={() => analyze(true)}
                disabled={!canAnalyze}
                className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] hover:border-[var(--primary)] transition cursor-pointer disabled:opacity-50"
              >
                Reanalizar todo
              </button>
            )}
            <button
              onClick={() => analyze(false)}
              disabled={!canAnalyze}
              className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-bold text-white shadow-xs hover:opacity-95 transition cursor-pointer disabled:opacity-50"
            >
              <Wand2 className="h-4 w-4" />
              {summary.has_candidates ? "Volver a buscar clips" : "Buscar clips"}
            </button>
          </div>
        </div>
        {activeJob ? (
          <JobProgress job={activeJob} />
        ) : (
          lastAnalysis?.status === "error" && <JobProgress job={lastAnalysis} />
        )}
        {error && (
          <p className="flex items-center gap-1.5 text-xs text-[var(--status-error)]">
            <AlertTriangle className="h-3.5 w-3.5" /> {error}
          </p>
        )}
      </div>

      {/* Source setup -------------------------------------------------------- */}
      <section className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-[var(--foreground)] flex items-center gap-2">
            <ScanFace className="h-4 w-4 text-[var(--primary)]" />
            {isComposite ? "Dónde está la cámara y el juego" : "Diálogos del juego en pantalla (opcional)"}
          </h2>
          {ingestReady && (
            <div className="flex flex-wrap gap-1.5">
              {pickerRegions.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setActive(r.key as RegionKey)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold border transition cursor-pointer ${
                    active === r.key ? "text-white" : "text-[var(--muted-foreground)] bg-[var(--secondary)] border-[var(--border)]"
                  }`}
                  style={active === r.key ? { backgroundColor: r.color, borderColor: r.color } : undefined}
                >
                  {r.label}
                  {r.rect ? " ✓" : ""}
                </button>
              ))}
            </div>
          )}
        </div>

        {!ingestReady ? (
          <p className="text-xs text-[var(--muted-foreground)]">
            {session.kick_url ? "Descargando el VOD de Kick para poder mostrar fotogramas…" : "Leyendo la fuente…"}
          </p>
        ) : (
          <>
            <p className="text-[11px] text-[var(--muted-foreground)]">
              {isComposite
                ? "Elige una región arriba y arrastra sobre el fotograma. Marca la cámara (solo la webcam) y el área del juego. Si el juego muestra sus diálogos como texto, marca también esa zona: ayuda a saber quién habla."
                : "Si el juego muestra sus diálogos como texto, arrastra sobre esa zona del gameplay. Ayuda a distinguir tu voz de la del juego."}
            </p>
            <div className={`grid gap-4 ${isComposite ? "" : "lg:grid-cols-[2fr_1fr]"}`}>
              <RegionPicker
                imageUrl={worker.frameUrl(id, "gameplay", frameT)}
                regions={pickerRegions}
                activeKey={active}
                onChange={(key, rect) => setRegions((prev) => ({ ...prev, [key as RegionKey]: rect }))}
              />
              {!isComposite && summary.source.camera && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={worker.frameUrl(id, "camera", frameT)}
                  alt="Fotograma de la cámara"
                  className="w-full rounded-2xl border border-[var(--border)]"
                />
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex-1 min-w-[200px] flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <Timer className="h-3.5 w-3.5" />
                <input
                  type="range"
                  min={0}
                  max={Math.max(1, Math.floor(duration))}
                  value={frameT}
                  onChange={(e) => setFrameT(Number(e.target.value))}
                  className="flex-1 accent-[var(--primary)]"
                />
                <span className="font-mono w-16 text-right">{formatClock(frameT)}</span>
              </label>
              <button
                onClick={saveSetup}
                disabled={saving || (isComposite && (!regions.camera || !regions.gameplay))}
                className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-white hover:opacity-95 transition cursor-pointer disabled:opacity-50"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                Guardar
              </button>
            </div>
          </>
        )}

        {!isComposite && (
          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-4 text-xs">
            <span className="font-semibold text-[var(--foreground)]">Sincronización cámara ↔ juego:</span>
            <span className="text-[var(--muted-foreground)]">
              {sync
                ? `${sync.method === "audio_xcorr" ? "por audio" : sync.method === "lipsync" ? "por labios" : sync.method === "manual" ? "manual" : "no encontrada"} · desfase ${sync.shift_sec.toFixed(2)} s · confianza ${Math.round(sync.confidence * 100)}%`
                : "se calcula al analizar"}
            </span>
            <input
              value={manualShift}
              onChange={(e) => setManualShift(e.target.value)}
              placeholder="desfase (s)"
              className="w-28 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
            />
            <button
              onClick={saveShift}
              className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-2.5 py-1.5 font-semibold text-[var(--foreground)] hover:border-[var(--primary)] cursor-pointer"
            >
              Fijar a mano
            </button>
            <span className="text-[11px] text-[var(--muted-foreground)]">
              Positivo si la cámara empezó a grabar antes que el juego.
            </span>
          </div>
        )}
      </section>

      {/* Candidates ---------------------------------------------------------- */}
      {candidates.length > 0 && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-[var(--foreground)]">Clips candidatos ({candidates.length})</h2>
            <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted-foreground)]">
              <Settings2 className="h-3.5 w-3.5" />
              <label className="flex items-center gap-1.5">
                Subtítulos
                <select
                  value={captions}
                  onChange={(e) => setCaptions(e.target.value as CaptionMode)}
                  className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2 py-1 text-[var(--foreground)]"
                >
                  <option value="streamer">Solo streamer</option>
                  <option value="all">Streamer + juego</option>
                  <option value="none">Sin subtítulos</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5">
                Título
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={titleSeconds}
                  onChange={(e) => setTitleSeconds(Number(e.target.value))}
                  className="w-14 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2 py-1 font-mono text-[var(--foreground)]"
                />
                s
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={punchIn} onChange={(e) => setPunchIn(e.target.checked)} className="accent-[var(--primary)]" />
                Zoom en la reacción
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={voiceBoost} onChange={(e) => setVoiceBoost(e.target.checked)} className="accent-[var(--primary)]" />
                Realzar voz
              </label>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {candidates.map((c, i) => (
              <CandidateCard key={c.id} candidate={c} rank={i + 1} job={renderJobs[c.id]} onRender={(edits) => render(c, edits)} />
            ))}
          </div>
        </section>
      )}

      {/* Rendered clips ------------------------------------------------------ */}
      {clips.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-bold text-[var(--foreground)] flex items-center gap-2">
            <Film className="h-4 w-4 text-[var(--primary)]" /> Shorts renderizados ({clips.length})
          </h2>
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            {[...clips].reverse().map((clip) => (
              <div key={clip.id} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-2 space-y-2">
                <video
                  src={worker.clipUrl(id, clip.id)}
                  controls
                  preload="metadata"
                  className="w-full aspect-[9/16] rounded-xl bg-black object-cover"
                />
                <div className="flex items-center justify-between gap-2 px-1">
                  <p className="text-[11px] font-semibold text-[var(--foreground)] truncate">{clip.overlay_title}</p>
                  <a
                    href={worker.clipUrl(id, clip.id, true)}
                    className="shrink-0 rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
                    title="Descargar"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
