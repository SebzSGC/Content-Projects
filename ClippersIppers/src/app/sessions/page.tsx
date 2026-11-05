"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Gamepad2, Camera, MonitorPlay, Link2, Plus, Loader2, AlertTriangle, ArrowRight, Film } from "lucide-react";
import type { SessionSummary, SourceMode } from "@/types/gaming";
import { worker, formatClock } from "@/lib/workerClient";
import { PathOrUpload } from "@/components/gaming/PathOrUpload";
import { JobProgress } from "@/components/gaming/JobProgress";

type CompositeSource = "kick" | "file";

export default function GamingSessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
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

  const tab = (active: boolean) =>
    `flex-1 inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition cursor-pointer ${
      active
        ? "bg-[var(--primary)] text-white shadow-xs"
        : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
    }`;

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="border-b border-[var(--border)] pb-5">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--foreground)] flex items-center gap-2.5">
          <Gamepad2 className="h-5 w-5 text-[var(--primary)]" />
          <span>Clips de gaming</span>
        </h1>
        <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
          Sube la grabación del stream y genera Shorts verticales con la cámara arriba y el juego abajo.
        </p>
        {aiLabel && (
          <p className="text-[11px] text-[var(--muted-foreground)] mt-1">
            IA configurada en el worker: <span className="font-mono">{aiLabel}</span> (cámbiala con CLIPS_LLM_PROVIDER / CLIPS_LLM_MODEL)
          </p>
        )}
      </div>

      {loadError && (
        <div className="rounded-2xl border border-[var(--status-warn)]/40 bg-[var(--status-warn-bg)] p-4 text-xs text-[var(--foreground)] flex gap-2">
          <AlertTriangle className="h-4 w-4 text-[var(--status-warn)] shrink-0" />
          <span>{loadError}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <form onSubmit={create} className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4 h-fit">
          <h2 className="text-sm font-bold text-[var(--foreground)] flex items-center gap-2">
            <Plus className="h-4 w-4 text-[var(--primary)]" /> Nueva sesión
          </h2>

          <div className="flex gap-2">
            <button type="button" className={tab(mode === "split")} onClick={() => setMode("split")}>
              <Camera className="h-3.5 w-3.5" /> Cámara + juego
            </button>
            <button type="button" className={tab(mode === "composite")} onClick={() => setMode("composite")}>
              <MonitorPlay className="h-3.5 w-3.5" /> Stream compuesto
            </button>
          </div>
          <p className="text-[11px] text-[var(--muted-foreground)]">
            {mode === "split"
              ? "Dos videos separados. El del juego debe traer el audio mezclado del stream; si la cámara también lo trae, la sincronización es exacta."
              : "Un solo video con la facecam encima del juego (VOD de Kick o grabación de OBS). Después marcarás dónde está la cámara."}
          </p>

          <label className="block space-y-1.5">
            <span className="text-xs font-semibold text-[var(--foreground)]">Título del stream (contexto para la IA)</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Le enseño a manejar a mi hermana en un simulador"
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
            />
          </label>

          {mode === "split" ? (
            <>
              <PathOrUpload
                label="Video del juego (con el audio mezclado)"
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
              <div className="flex gap-2">
                <button type="button" className={tab(compositeSource === "kick")} onClick={() => setCompositeSource("kick")}>
                  <Link2 className="h-3.5 w-3.5" /> Link de Kick
                </button>
                <button type="button" className={tab(compositeSource === "file")} onClick={() => setCompositeSource("file")}>
                  <Film className="h-3.5 w-3.5" /> Archivo .mp4 / .mkv
                </button>
              </div>
              {compositeSource === "kick" ? (
                <label className="block space-y-1.5">
                  <span className="text-xs font-semibold text-[var(--foreground)]">VOD o clip de Kick</span>
                  <input
                    value={kickUrl}
                    onChange={(e) => setKickUrl(e.target.value)}
                    placeholder="https://kick.com/canal/videos/…"
                    className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
                  />
                </label>
              ) : (
                <PathOrUpload label="Video completo del stream" value={gameplayPath} onChange={setGameplayPath} />
              )}
            </>
          )}

          <label className="block space-y-1.5">
            <span className="text-xs font-semibold text-[var(--foreground)]">Voz del streamer (opcional)</span>
            <select
              value={voiceprint}
              onChange={(e) => setVoiceprint(e.target.value)}
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
            >
              <option value="">Sin huella de voz</option>
              {voiceprints.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>

          {createError && <p className="text-xs text-[var(--status-error)]">{createError}</p>}

          <button
            type="submit"
            disabled={creating}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--primary)] px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:opacity-95 transition cursor-pointer disabled:opacity-60"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Crear sesión
          </button>
        </form>

        <div className="space-y-3">
          {sessions.length === 0 && !loadError && (
            <div className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-12 text-center space-y-2">
              <Gamepad2 className="h-10 w-10 text-[var(--muted-foreground)] mx-auto opacity-40" />
              <p className="text-sm font-bold text-[var(--foreground)]">Todavía no hay sesiones</p>
              <p className="text-xs text-[var(--muted-foreground)]">Crea una con la grabación de tu stream.</p>
            </div>
          )}
          {sessions.map((s) => {
            const job = s.jobs.find((j) => j.status === "running" || j.status === "queued") || s.jobs[0];
            return (
              <Link
                key={s.session.id}
                href={`/sessions/${s.session.id}`}
                className="block rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 hover:border-[var(--primary)] transition space-y-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-[var(--foreground)] truncate">
                      {s.session.title || s.session.kick_url || s.session.gameplay_path?.split(/[\\/]/).pop() || s.session.id}
                    </p>
                    <p className="text-[11px] text-[var(--muted-foreground)]">
                      {s.session.mode === "split" ? "Cámara + juego" : s.session.kick_url ? "Kick" : "Stream compuesto"}
                      {s.manifest ? ` · ${formatClock(s.manifest.gameplay.duration)}` : ""}
                      {` · ${s.candidates} candidatos · ${s.clips} clips`}
                    </p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-[var(--muted-foreground)] shrink-0" />
                </div>
                {job && job.status !== "done" && <JobProgress job={job} compact />}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
