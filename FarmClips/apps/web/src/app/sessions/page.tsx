"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bell,
  CheckCircle2,
  Clock,
  FolderSync,
  Gamepad2,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  Video,
  XCircle,
} from "lucide-react";
import {
  createSession,
  fetchDriveStatus,
  fetchKeytermsPreview,
  fetchMaintenanceStats,
  fetchSessions,
  triggerDrivePoll,
  triggerMaintenanceCleanup,
  triggerTestWebhook,
  uploadVideoFile,
  useServerEvents,
  type DriveStatus,
  type KeytermsPreviewPayload,
  type MaintenanceStats,
  type SessionSummary,
} from "@/lib/api/client";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function stateBadge(state: string) {
  switch (state) {
    case "DELIVERED":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/30">
          <CheckCircle2 className="h-3 w-3" /> Entregado
        </span>
      );
    case "FAILED":
    case "CANCELLED":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-red-300 ring-1 ring-red-500/30">
          <XCircle className="h-3 w-3" /> {state}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2.5 py-0.5 text-[11px] font-semibold text-amber-300 ring-1 ring-amber-400/30">
          <Loader2 className="h-3 w-3 animate-spin" /> {state}
        </span>
      );
  }
}

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [drive, setDrive] = useState<DriveStatus | null>(null);
  const [maint, setMaint] = useState<MaintenanceStats | null>(null);
  const [keytermsInfo, setKeytermsInfo] = useState<KeytermsPreviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [pollingDrive, setPollingDrive] = useState(false);
  const [cleaningUp, setCleaningUp] = useState(false);
  const [webhookUrlInput, setWebhookUrlInput] = useState("");
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [maintMsg, setMaintMsg] = useState<string | null>(null);
  const [liveMessages, setLiveMessages] = useState<Record<string, string>>({});

  // Form state
  const [mode, setMode] = useState<"local" | "upload">("local");
  const [title, setTitle] = useState("");
  const [gameplayPath, setGameplayPath] = useState("");
  const [cameraPath, setCameraPath] = useState("");
  const [gameplayFile, setGameplayFile] = useState<File | null>(null);
  const [cameraFile, setCameraFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [sesList, drv, mStats] = await Promise.all([
        fetchSessions(),
        fetchDriveStatus(),
        fetchMaintenanceStats().catch(() => null),
      ]);
      setSessions(sesList);
      setDrive(drv);
      setMaint(mStats);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const handle = setTimeout(() => {
      fetchKeytermsPreview(title)
        .then(setKeytermsInfo)
        .catch(() => null);
    }, 200);
    return () => clearTimeout(handle);
  }, [title]);

  useServerEvents(undefined, (ev) => {
    if (ev.session_id && ev.message) {
      setLiveMessages((prev) => ({ ...prev, [ev.session_id!]: ev.message! }));
    }
    if (ev.type === "session_state" || ev.type === "clip_updated") {
      reload();
    }
  });

  async function handleCreateSession(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      let gp = gameplayPath.trim();
      let cm = cameraPath.trim();
      if (mode === "upload") {
        if (!gameplayFile || !cameraFile) {
          throw new Error("Selecciona ambos archivos: gameplay.mp4 y camara.mp4.");
        }
        const [upGp, upCm] = await Promise.all([
          uploadVideoFile(gameplayFile),
          uploadVideoFile(cameraFile),
        ]);
        gp = upGp.path;
        cm = upCm.path;
      } else if (!gp || !cm) {
        throw new Error("Indica las rutas locales de gameplay.mp4 y camara.mp4.");
      }

      const created = await createSession({
        title: title.trim() || "Sesión Gaming",
        gameplay_path: gp,
        camera_path: cm,
        recording_name: title.trim() || undefined,
        language: "es",
        style_preset: "hormozi-gaming",
        auto_start: true,
      });
      router.push(`/sessions/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePollDrive() {
    setPollingDrive(true);
    setError(null);
    try {
      const res = await triggerDrivePoll();
      await reload();
      if (res.launched_sessions.length > 0) {
        router.push(`/sessions/${res.launched_sessions[0]}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPollingDrive(false);
    }
  }

  function fillGoldenPaths() {
    setMode("local");
    setTitle("Valorant Torneo Final — Golden 1v3");
    setGameplayPath("tests/golden/gameplay.mp4");
    setCameraPath("tests/golden/camara.mp4");
  }

  async function handleCleanupNow() {
    setCleaningUp(true);
    setMaintMsg(null);
    try {
      const res = await triggerMaintenanceCleanup(0, false);
      setMaintMsg(
        res.purged_files > 0
          ? `Liberados ${formatBytes(res.freed_bytes)} (${res.purged_files} temporales WAV/Opus; caché $0 intacta).`
          : "No había temporales pendientes en sesiones entregadas."
      );
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCleaningUp(false);
    }
  }

  async function handleTestWebhook() {
    setTestingWebhook(true);
    setMaintMsg(null);
    try {
      const res = await triggerTestWebhook(webhookUrlInput.trim() || undefined);
      setMaintMsg(
        res.ok
          ? `Webhook (${res.format}) enviado con éxito (HTTP ${res.status_code}).`
          : `Respuesta Webhook (${res.format}): HTTP ${res.status_code}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTestingWebhook(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* Hero & Architecture Principles Banner */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-zinc-800/90 bg-gradient-to-br from-zinc-900/90 via-[#0E1018] to-zinc-950 p-6 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">
            Sesiones de Grabación Separada (<span className="text-[#FFD400]">Juego</span> +{" "}
            <span className="text-[#39FF14]">Cámara</span>)
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-zinc-400">
            Solo viaja audio Opus mono 16 kHz (~7 MB/h) y texto compacto a la nube. El video permanece 100 % local:
            sincronización FFT, tracking facial MediaPipe en CPU por clip, EditPlan declarativo v2 y render NVENC en
            1080×1920 (−14 LUFS).
          </p>
        </div>
        <button
          type="button"
          onClick={fillGoldenPaths}
          className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-[#FFD400]/40 bg-[#FFD400]/10 px-4 py-2.5 text-xs font-bold text-[#FFD400] transition hover:bg-[#FFD400]/20"
        >
          <Sparkles className="h-4 w-4" /> Cargar grabación de prueba (Golden)
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* New Session Card */}
        <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-base font-bold text-white">
              <Video className="h-4 w-4 text-[#FFD400]" /> Nueva sesión manual
            </h2>
            <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setMode("local")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition ${
                  mode === "local" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <HardDrive className="h-3.5 w-3.5" /> Rutas locales
              </button>
              <button
                type="button"
                onClick={() => setMode("upload")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition ${
                  mode === "upload" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Upload className="h-3.5 w-3.5" /> Subir archivos
              </button>
            </div>
          </div>

          <form onSubmit={handleCreateSession} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-400">
                Nombre / Juego de la grabación (ayuda a los keyterms de Deepgram Nova-3 y al LLM)
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ej. Valorant Ranked Inmortal — Sesión Noche"
                className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm text-white placeholder-zinc-600 focus:border-[#FFD400] focus:outline-none"
              />
              {keytermsInfo && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                  {keytermsInfo.detected_game ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-[#39FF14]/15 px-2.5 py-0.5 font-bold text-[#39FF14] ring-1 ring-[#39FF14]/30">
                      <Gamepad2 className="h-3 w-3" /> Perfil autodetectado: {keytermsInfo.detected_game.toUpperCase()}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-0.5 font-medium text-zinc-300">
                      <Gamepad2 className="h-3 w-3 text-[#FFD400]" /> Vocabulario general ES gaming (escribe Valorant, LoL, CS2, Fortnite, Warzone, Minecraft…)
                    </span>
                  )}
                  <span className="truncate text-zinc-500">
                    {keytermsInfo.resolved_keyterms.length} keyterms → {keytermsInfo.resolved_keyterms.slice(0, 6).join(", ")}…
                  </span>
                </div>
              )}
            </div>

            {mode === "local" ? (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-400">
                    Ruta de <code className="text-[#FFD400]">gameplay.mp4</code> (16:9 + mezcla/juego)
                  </label>
                  <input
                    type="text"
                    value={gameplayPath}
                    onChange={(e) => setGameplayPath(e.target.value)}
                    placeholder="C:\Grabaciones\sesion_01\gameplay.mp4"
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-2 font-mono text-xs text-white placeholder-zinc-600 focus:border-[#FFD400] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-400">
                    Ruta de <code className="text-[#39FF14]">camara.mp4</code> (rostro + micrófono limpio)
                  </label>
                  <input
                    type="text"
                    value={cameraPath}
                    onChange={(e) => setCameraPath(e.target.value)}
                    placeholder="C:\Grabaciones\sesion_01\camara.mp4"
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-2 font-mono text-xs text-white placeholder-zinc-600 focus:border-[#39FF14] focus:outline-none"
                  />
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-950/70 p-4 text-center hover:border-[#FFD400]">
                  <span className="text-xs font-semibold text-[#FFD400]">Archivo Gameplay (MP4/MKV)</span>
                  <span className="mt-1 text-[11px] text-zinc-400">
                    {gameplayFile ? gameplayFile.name : "Haz clic para elegir gameplay.mp4"}
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => setGameplayFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-950/70 p-4 text-center hover:border-[#39FF14]">
                  <span className="text-xs font-semibold text-[#39FF14]">Archivo Cámara + Micrófono</span>
                  <span className="mt-1 text-[11px] text-zinc-400">
                    {cameraFile ? cameraFile.name : "Haz clic para elegir camara.mp4"}
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => setCameraFile(e.target.files?.[0] ?? null)}
                  />
                </label>
              </div>
            )}

            <div className="flex items-center justify-between pt-1">
              <span className="text-xs text-zinc-500">
                Preset activo: <strong className="text-zinc-300">hormozi-gaming</strong> · Top 5 (&gt;60/100) se
                renderizan solos en 1080p
              </span>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-[#FFD400] px-5 py-2.5 text-xs font-extrabold text-black transition hover:bg-amber-300 disabled:opacity-50"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-black" />}
                Iniciar Pipeline Híbrido
              </button>
            </div>
          </form>
        </div>

        {/* Google Drive Watcher Card */}
        <div className="flex flex-col justify-between rounded-2xl border border-zinc-800 bg-[#0E1017] p-5">
          <div>
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-base font-bold text-white">
                <FolderSync className="h-4 w-4 text-[#39FF14]" /> Google Drive (Entradas → Salidas)
              </h2>
              <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-300">
                {drive?.mode ?? "local"}
              </span>
            </div>
            <p className="mt-2 text-xs text-zinc-400">
              Vigila <code className="text-zinc-200">Entradas/&lt;grabación&gt;/</code> esperando tamaño estable en 2
              revisiones seguidas, descarga por streaming y publica los 5 mejores clips + JSON en{" "}
              <code className="text-zinc-200">Salidas/&lt;grabación&gt;/</code>.
            </p>

            {drive && (
              <div className="mt-4 space-y-2 rounded-xl border border-zinc-800/80 bg-zinc-950/70 p-3 text-xs">
                <div className="truncate font-mono text-[11px] text-zinc-400" title={drive.local_dir}>
                  Raíz: {drive.local_dir}
                </div>
                <div className="flex justify-between text-zinc-300">
                  <span>Carpetas en Entradas/:</span>
                  <strong className="text-[#FFD400]">{drive.entradas.length}</strong>
                </div>
                <div className="flex justify-between text-zinc-300">
                  <span>Carpetas entregadas en Salidas/:</span>
                  <strong className="text-[#39FF14]">{drive.salidas.length}</strong>
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={handlePollDrive}
            disabled={pollingDrive}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-xs font-bold text-white transition hover:border-zinc-500 hover:bg-zinc-800 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${pollingDrive ? "animate-spin" : ""}`} />
            Revisar Entradas/ ahora
          </button>
        </div>
      </div>

      {/* Sessions List */}
      <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-bold text-white">Sesiones procesadas y en curso</h2>
          <button
            type="button"
            onClick={reload}
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Actualizar
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-sm text-zinc-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando sesiones…
          </div>
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
            Aún no hay sesiones. Usa el botón{" "}
            <button type="button" onClick={fillGoldenPaths} className="font-semibold text-[#FFD400] underline">
              Cargar grabación de prueba (Golden)
            </button>{" "}
            o coloca una carpeta con <code>gameplay.mp4</code> y <code>camara.mp4</code> en <code>Entradas/</code>.
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/80">
            {sessions.map((s) => (
              <Link
                key={s.id}
                href={`/sessions/${s.id}`}
                className="flex flex-col justify-between gap-3 py-4 transition hover:bg-zinc-900/40 sm:flex-row sm:items-center sm:px-3 rounded-xl"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="font-bold text-white">{s.title}</span>
                    {stateBadge(s.state)}
                    {s.detected_game && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-[#39FF14]/10 px-2 py-0.5 text-[10px] font-bold uppercase text-[#39FF14] ring-1 ring-[#39FF14]/30">
                        <Gamepad2 className="h-3 w-3" /> {s.detected_game}
                      </span>
                    )}
                    <span className="font-mono text-[11px] text-zinc-500">{s.id}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" /> {new Date(s.created_at * 1000).toLocaleString()}
                    </span>
                    {s.sync && (
                      <span>
                        Sync: <strong className="text-zinc-200">{s.sync.method}</strong> (
                        {s.sync.shift_sec >= 0 ? "+" : ""}
                        {s.sync.shift_sec.toFixed(2)}s)
                      </span>
                    )}
                    {liveMessages[s.id] && <span className="text-[#FFD400]">· {liveMessages[s.id]}</span>}
                    {s.error && <span className="text-red-400">· {s.error}</span>}
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs">
                  <div className="text-right">
                    <div className="font-bold text-white">{s.clips_count} clips curados</div>
                    <div className="text-zinc-500">{s.rendered_count} renderizados en 1080p</div>
                  </div>
                  <span className="rounded-lg bg-zinc-800 px-3 py-1.5 font-semibold text-zinc-200">Abrir →</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
      {/* Storage TTL Maintenance & Delivery Webhooks */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-bold text-white">
              <Trash2 className="h-4 w-4 text-[#FFD400]" /> Limpieza TTL de Temporales (Conserva Caché $0)
            </h2>
            <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-300">
              TTL automático: {maint?.temp_ttl_days ?? 7}d
            </span>
          </div>
          <p className="mt-1.5 text-xs text-zinc-400">
            Elimina WAV/Opus intermedios de sesiones entregadas manteniendo intactos{" "}
            <code className="text-zinc-200">Parquet</code>, <code className="text-zinc-200">EditPlan</code>,{" "}
            <code className="text-zinc-200">raw_api</code> y SQLite.
          </p>
          {maint && (
            <div className="mt-3 grid grid-cols-3 gap-2 rounded-xl border border-zinc-800/80 bg-zinc-950/70 p-3 text-center text-xs">
              <div>
                <div className="text-[10px] text-zinc-500">WAV/Opus Temp</div>
                <div className="font-mono font-bold text-[#FFD400]">{formatBytes(maint.temp_media_bytes)}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-500">Renders MP4</div>
                <div className="font-mono font-bold text-white">{formatBytes(maint.renders_bytes)}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-500">Caché $0 Protegida</div>
                <div className="font-mono font-bold text-[#39FF14]">{formatBytes(maint.preserved_cache_bytes)}</div>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={handleCleanupNow}
            disabled={cleaningUp}
            className="mt-3 inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900 px-3.5 py-2 text-xs font-bold text-white hover:bg-zinc-800 disabled:opacity-50"
          >
            {cleaningUp ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Purgar WAV/Opus de sesiones entregadas ahora
          </button>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-[#0E1017] p-5">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-bold text-white">
              <Bell className="h-4 w-4 text-[#39FF14]" /> Notificaciones Webhook (Discord / Slack / HTTP)
            </h2>
            <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-300">
              {maint?.webhook_configured ? "CLIPS_WEBHOOK_URL activa" : "Prueba bajo demanda"}
            </span>
          </div>
          <p className="mt-1.5 text-xs text-zinc-400">
            Al terminar una sesión en <code className="text-zinc-200">Salidas/</code>, envía el resumen de los mejores
            clips con enlaces directos al editor.
          </p>
          <div className="mt-3 flex gap-2">
            <input
              type="url"
              value={webhookUrlInput}
              onChange={(e) => setWebhookUrlInput(e.target.value)}
              placeholder="https://discord.com/api/webhooks/... o hooks.slack.com/..."
              className="flex-1 rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-white placeholder-zinc-600 focus:border-[#39FF14] focus:outline-none"
            />
            <button
              type="button"
              onClick={handleTestWebhook}
              disabled={testingWebhook}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-[#39FF14]/15 px-3.5 py-2 text-xs font-bold text-[#39FF14] ring-1 ring-[#39FF14]/40 hover:bg-[#39FF14]/25 disabled:opacity-50"
            >
              {testingWebhook ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bell className="h-3.5 w-3.5" />}
              Probar
            </button>
          </div>
          {maintMsg && <p className="mt-2 text-xs font-medium text-[#39FF14]">{maintMsg}</p>}
        </div>
      </div>
    </div>
  );
}
