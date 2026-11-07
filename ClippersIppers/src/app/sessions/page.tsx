"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Gamepad2, Camera, MonitorPlay, Link2, Plus, AlertTriangle, ChevronRight, Film, Sparkles } from "lucide-react";
import type { SessionSummary, SourceMode } from "@/types/gaming";
import { worker, formatClock } from "@/lib/workerClient";
import { computeSteps } from "@/lib/gamingSteps";
import { PathOrUpload } from "@/components/gaming/PathOrUpload";
import { StepProgress } from "@/components/gaming/StepProgress";
import { Badge, GlassCard, InfoTip, Segmented, SoftSpinner, btnPrimary, inputBase } from "@/components/gaming/ui";

type CompositeSource = "kick" | "file";

function sessionName(s: SessionSummary): string {
  return s.session.title || s.session.kick_url || s.session.gameplay_path?.split(/[\\/]/).pop() || s.session.id;
}

function statusBadge(s: SessionSummary) {
  const running = s.jobs.find((j) => j.status === "running" || j.status === "queued");
  if (running) return <Badge tone="gold"><SoftSpinner className="h-3 w-3" /> Procesando</Badge>;
  if (s.jobs[0]?.status === "error") return <Badge tone="danger">Con error</Badge>;
  if (s.clips > 0) return <Badge tone="success">{s.clips} Shorts</Badge>;
  if (s.candidates > 0) return <Badge tone="info">{s.candidates} candidatos</Badge>;
  return <Badge>Por analizar</Badge>;
}

export default function GamingSessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [voiceprints, setVoiceprints] = useState<string[]>([]);
  const [aiLabel, setAiLabel] = useState<string | null>(null);

  const [mode, setMode] = useState<SourceMode>("split");
  const [compositeSource, setCompositeSource] = useState<CompositeSource>("kick");
  const [title, setTitle] = useState("");
  const [gameplayPath, setGameplayPath] = useState("");
  const [cameraPath, setCameraPath] = useState("");
  const [kickUrl, setKickUrl] = useState("");
  const [voiceprint, setVoiceprint] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSessions(await worker.listSessions());
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "No se pudo contactar al worker");
      setSessions((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => {
    refresh();
    worker.voiceprints().then(setVoiceprints).catch(() => setVoiceprints([]));
    worker
      .health()
      .then((h) => setAiLabel(`${h.llm_provider} · ${h.llm_model}${h.llm_vision ? "" : " (sin imágenes)"}`))
      .catch(() => setAiLabel(null));
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const { session } = await worker.createSession({
        mode,
        title,
        language: "es",
        voiceprint: voiceprint || undefined,
        gameplay_path: mode === "split" || compositeSource === "file" ? gameplayPath : undefined,
        camera_path: mode === "split" ? cameraPath : undefined,
        kick_url: mode === "composite" && compositeSource === "kick" ? kickUrl : undefined,
      });
      router.push(`/sessions/${session.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "No se pudo crear la sesión");
      setCreating(false);
    }
  };

  const ready =
    mode === "split" ? Boolean(gameplayPath && cameraPath) : compositeSource === "kick" ? Boolean(kickUrl) : Boolean(gameplayPath);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 inline-flex items-center gap-2 rounded-full bg-amber-400/10 px-3 py-1 text-xs font-bold text-amber-300">
            <Gamepad2 className="h-3.5 w-3.5" /> Estudio de clips
          </p>
          <h1 className="text-3xl font-black tracking-tight text-slate-50 sm:text-4xl">Tus streams, en Shorts</h1>
          <p className="mt-2 max-w-xl text-base text-slate-400">
            Sube la grabación y te proponemos los mejores momentos con la cámara arriba y el juego abajo.
          </p>
        </div>
        {aiLabel && (
          <span className="inline-flex items-center gap-1 self-start rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-400 sm:self-auto">
            <Sparkles className="h-3.5 w-3.5 text-amber-300" /> IA lista
            <InfoTip label="Modelo de IA configurado">
              Proveedor y modelo: <span className="font-mono text-slate-200">{aiLabel}</span>. Se cambia en el worker con CLIPS_LLM_PROVIDER y CLIPS_LLM_MODEL.
            </InfoTip>
          </span>
        )}
      </header>

      {loadError && (
        <div className="flex items-start gap-3 rounded-3xl border border-amber-300/20 bg-amber-400/10 p-4 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <span>{loadError}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <GlassCard as="form" onSubmit={create} className="h-fit space-y-5 p-6">
          <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-50">
            <Plus className="h-5 w-5 text-amber-300" /> Nueva sesión
          </h2>

          <Segmented
            className="w-full"
            value={mode}
            onChange={setMode}
            options={[
              { value: "split", label: <><Camera className="h-3.5 w-3.5" /> Cámara + juego</> },
              { value: "composite", label: <><MonitorPlay className="h-3.5 w-3.5" /> Stream completo</> },
            ]}
          />
          <p className="text-sm text-slate-400">
            {mode === "split"
              ? "Dos videos: el del juego (con el audio del stream) y el de tu cámara."
              : "Un solo video con la cámara encima del juego. Después marcarás dónde está cada cosa."}
          </p>

          <label className="block space-y-2">
            <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
              ¿De qué trata el stream?
              <InfoTip>Le da contexto a la IA para elegir momentos y escribir títulos.</InfoTip>
            </span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Le enseño a manejar a mi hermana" className={inputBase} />
          </label>

          {mode === "split" ? (
            <>
              <PathOrUpload
                label="Video del juego"
                hint="Debe traer el audio mezclado del stream. Si la cámara también lo trae, la sincronización es exacta."
                value={gameplayPath}
                onChange={setGameplayPath}
              />
              <PathOrUpload
                label="Video de la cámara"
                hint="Grabado con el plugin Source Record de OBS en la misma sesión."
                value={cameraPath}
                onChange={setCameraPath}
              />
            </>
          ) : (
            <>
              <Segmented
                className="w-full"
                value={compositeSource}
                onChange={setCompositeSource}
                options={[
                  { value: "kick", label: <><Link2 className="h-3.5 w-3.5" /> Link de Kick</> },
                  { value: "file", label: <><Film className="h-3.5 w-3.5" /> Archivo</> },
                ]}
              />
              {compositeSource === "kick" ? (
                <label className="block space-y-2">
                  <span className="text-sm font-bold text-slate-200">VOD o clip de Kick</span>
                  <input value={kickUrl} onChange={(e) => setKickUrl(e.target.value)} placeholder="https://kick.com/canal/videos/…" className={`${inputBase} font-mono text-xs`} />
                </label>
              ) : (
                <PathOrUpload label="Video completo del stream" value={gameplayPath} onChange={setGameplayPath} />
              )}
            </>
          )}

          <label className="block space-y-2">
            <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
              Tu voz <span className="font-semibold text-slate-500">(opcional)</span>
              <InfoTip>Una huella de tu voz ayuda a distinguirte de los personajes del juego cuando no se te ve la cara.</InfoTip>
            </span>
            <select value={voiceprint} onChange={(e) => setVoiceprint(e.target.value)} className={inputBase}>
              <option value="">Sin huella de voz</option>
              {voiceprints.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>

          {createError && <p className="rounded-2xl bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-200">{createError}</p>}

          <button type="submit" disabled={creating || !ready} className={`${btnPrimary} w-full`}>
            {creating ? <SoftSpinner onAccent className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
            Crear sesión
          </button>
        </GlassCard>

        <section className="space-y-4" aria-label="Sesiones">
          {sessions === null &&
            [0, 1, 2].map((i) => <div key={i} className="h-28 animate-pulse rounded-3xl bg-slate-800/40 motion-reduce:animate-none" />)}

          {sessions?.length === 0 && !loadError && (
            <GlassCard className="flex flex-col items-center gap-3 p-12 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-amber-400/10">
                <Gamepad2 className="h-7 w-7 text-amber-300" />
              </span>
              <p className="text-lg font-extrabold text-slate-100">Todavía no hay sesiones</p>
              <p className="text-sm text-slate-400">Crea la primera con la grabación de tu stream.</p>
            </GlassCard>
          )}

          {sessions?.map((s) => {
            const running = s.jobs.find((j) => j.status === "running" || j.status === "queued");
            return (
              <Link key={s.session.id} href={`/sessions/${s.session.id}`} className="block rounded-3xl focus:outline-none focus-visible:ring-4 focus-visible:ring-amber-400/30">
                <GlassCard interactive className="space-y-4 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-extrabold text-slate-50">{sessionName(s)}</p>
                      <p className="mt-0.5 text-sm text-slate-400">
                        {s.session.mode === "split" ? "Cámara + juego" : s.session.kick_url ? "Kick" : "Stream completo"}
                        {s.manifest ? ` · ${formatClock(s.manifest.gameplay.duration)}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {statusBadge(s)}
                      <ChevronRight className="h-4 w-4 text-slate-500" />
                    </div>
                  </div>
                  <StepProgress state={computeSteps(s)} compact />
                  {running && running.stage && (
                    <p className="text-xs font-semibold text-slate-400">{Math.round(running.progress * 100)}% completado</p>
                  )}
                </GlassCard>
              </Link>
            );
          })}
        </section>
      </div>
    </div>
  );
}
