"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bell,
  Camera,
  CheckCircle2,
  ChevronRight,
  Clock,
  Film,
  Folder,
  FolderSync,
  Gamepad2,
  HardDrive,
  Link2,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  Wrench,
} from "lucide-react";
import {
  createDriveSession,
  createSession,
  fetchDriveAuthUrl,
  fetchDriveFiles,
  fetchDriveStatus,
  fetchKeytermsPreview,
  fetchMaintenanceStats,
  fetchSessions,
  triggerDrivePoll,
  triggerMaintenanceCleanup,
  triggerTestWebhook,
  uploadVideoFile,
  useServerEvents,
  type DriveBrowseResponse,
  type DriveStatus,
  type DriveVideoItem,
  type KeytermsPreviewPayload,
  type MaintenanceStats,
  type SessionSummary,
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
  SectionHeader,
  Segmented,
  SoftSpinner,
  StatusDot,
  btnGhost,
  btnPrimary,
  btnSecondary,
  inputBase,
} from "@/components/ui";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function stateBadge(state: string) {
  if (state === "DELIVERED") return <Badge tone="success">{friendlyState(state)}</Badge>;
  if (state === "FAILED") return <Badge tone="danger">{friendlyState(state)}</Badge>;
  if (state === "CANCELLED") return <Badge>{friendlyState(state)}</Badge>;
  return (
    <Badge tone="gold">
      <SoftSpinner className="h-3 w-3" /> {friendlyState(state)}
    </Badge>
  );
}

function FilePick({
  label,
  hint,
  file,
  onPick,
}: {
  label: string;
  hint: string;
  file: File | null;
  onPick: (f: File | null) => void;
}) {
  return (
    <label className="group flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-white/[0.14] bg-[#0e1016] p-5 text-center transition-colors duration-150 hover:border-amber-400/45 hover:bg-[#12151e]">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-slate-400 transition-colors duration-150 group-hover:border-amber-400/30 group-hover:text-amber-300">
        <Upload className="h-4 w-4" />
      </span>
      <span className="text-xs sm:text-sm font-semibold text-slate-100">{label}</span>
      <span className="max-w-full truncate font-mono text-[11px] text-slate-400">
        {file ? file.name : hint}
      </span>
      <input
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
    </label>
  );
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

  // Session filter & search
  const [sessionFilter, setSessionFilter] = useState<"all" | "running" | "delivered" | "failed">("all");
  const [sessionQuery, setSessionQuery] = useState("");

  // Form state
  const [mode, setMode] = useState<"local" | "upload" | "drive">("local");
  const [title, setTitle] = useState("");
  const [gameplayPath, setGameplayPath] = useState("");
  const [cameraPath, setCameraPath] = useState("");
  const [gameplayFile, setGameplayFile] = useState<File | null>(null);
  const [cameraFile, setCameraFile] = useState<File | null>(null);
  const [maxClips, setMaxClips] = useState<number>(5);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Interactive Google Drive Explorer state
  const [driveBrowser, setDriveBrowser] = useState<DriveBrowseResponse | null>(null);
  const [driveFolderId, setDriveFolderId] = useState<string | undefined>(undefined);
  const [driveSearch, setDriveSearch] = useState("");
  const [loadingDriveFiles, setLoadingDriveFiles] = useState(false);
  const [driveBrowserError, setDriveBrowserError] = useState<string | null>(null);
  const [driveGameplay, setDriveGameplay] = useState<DriveVideoItem | null>(null);
  const [driveCamera, setDriveCamera] = useState<DriveVideoItem | null>(null);

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

  const loadDriveFolder = useCallback(async (folderId?: string, query?: string) => {
    setLoadingDriveFiles(true);
    setDriveBrowserError(null);
    try {
      const res = await fetchDriveFiles(folderId, query);
      setDriveBrowser(res);
      setDriveFolderId(res.folder_id);
      if (res.detected_pair) {
        setDriveGameplay(res.detected_pair.gameplay);
        setDriveCamera(res.detected_pair.camera);
        setTitle((prev) =>
          prev.trim()
            ? prev
            : res.detected_pair?.recording_name &&
                res.detected_pair.recording_name !== "Raíz local" &&
                res.detected_pair.recording_name !== "Mi unidad"
              ? res.detected_pair.recording_name
              : prev
        );
      }
    } catch (err) {
      setDriveBrowserError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingDriveFiles(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (mode !== "drive") return;
    const handle = setTimeout(() => {
      loadDriveFolder(driveFolderId, driveSearch);
    }, 180);
    return () => clearTimeout(handle);
  }, [mode, driveFolderId, driveSearch, loadDriveFolder]);

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
    if (ev.type === "session_state" || ev.type === "clip_updated" || ev.type === "drive_auth_updated") {
      reload();
    }
  });

  async function handleConnectDriveOAuth() {
    setError(null);
    try {
      const res = await fetchDriveAuthUrl();
      window.open(res.auth_url, "_blank", "noopener,noreferrer,width=560,height=680");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function handleSelectDetectedPair() {
    if (!driveBrowser?.detected_pair) return;
    setDriveGameplay(driveBrowser.detected_pair.gameplay);
    setDriveCamera(driveBrowser.detected_pair.camera);
    if (!title.trim() && driveBrowser.detected_pair.recording_name) {
      setTitle(driveBrowser.detected_pair.recording_name);
    }
  }

  async function handleCreateSession(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "drive") {
        const gp = driveGameplay ?? driveBrowser?.detected_pair?.gameplay ?? null;
        const cm = driveCamera ?? driveBrowser?.detected_pair?.camera ?? null;
        if (!gp || !cm) {
          throw new Error(
            "Selecciona los videos de Juego (gameplay) y Cámara desde el explorador de Google Drive."
          );
        }
        if (gp.id === cm.id) {
          throw new Error("El video de gameplay y el de cámara deben ser archivos distintos.");
        }
        const recName = title.trim() || driveBrowser?.folder_name || "Sesión Drive";
        const safeMaxClips = Math.max(1, Math.min(20, Math.round(Number(maxClips) || 5)));
        const created = await createDriveSession({
          title: recName,
          folder_id: driveBrowser?.folder_id,
          gameplay_file_id: gp.id,
          camera_file_id: cm.id,
          recording_name: recName,
          language: "es",
          style_preset: "hormozi-gaming",
          max_clips: safeMaxClips,
          auto_start: true,
        });
        router.push(`/sessions/${created.id}`);
        return;
      }

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

      const safeMaxClips = Math.max(1, Math.min(20, Math.round(Number(maxClips) || 5)));
      const created = await createSession({
        title: title.trim() || "Sesión Gaming",
        gameplay_path: gp,
        camera_path: cm,
        recording_name: title.trim() || undefined,
        language: "es",
        style_preset: "hormozi-gaming",
        max_clips: safeMaxClips,
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

  const activeCount = sessions.filter((s) => sessionSteps(s).running).length;
  const deliveredCount = sessions.filter((s) => s.state === "DELIVERED").length;
  const failedCount = sessions.filter((s) => s.state === "FAILED").length;

  const filteredSessions = useMemo(() => {
    return sessions.filter((s) => {
      const steps = sessionSteps(s);
      if (sessionFilter === "running" && !steps.running) return false;
      if (sessionFilter === "delivered" && s.state !== "DELIVERED") return false;
      if (sessionFilter === "failed" && s.state !== "FAILED") return false;
      if (sessionQuery.trim()) {
        const q = sessionQuery.trim().toLowerCase();
        const inTitle = s.title.toLowerCase().includes(q);
        const inGame = (s.detected_game ?? "").toLowerCase().includes(q);
        const inId = s.id.toLowerCase().includes(q);
        if (!inTitle && !inGame && !inId) return false;
      }
      return true;
    });
  }, [sessions, sessionFilter, sessionQuery]);

  return (
    <div className="space-y-6">
      {/* Studio Workspace Header */}
      <SectionHeader
        eyebrow={
          <>
            <Gamepad2 className="h-3.5 w-3.5" /> Estudio de producción · 9:16 Vertical
          </>
        }
        title={
          <span className="inline-flex items-center gap-2">
            Tus partidas, listas para Shorts
            <InfoTip label="¿Por qué es rápido y económico?">
              Tus videos pesados nunca suben a internet: se editan en tu propio equipo. A la nube solo enviamos una pista
              de voz muy ligera para entender qué dijiste y elegir los mejores momentos.
            </InfoTip>
          </span>
        }
        description="Combina el video del juego y el de tu cámara: detectamos las jugadas clave, centramos tu rostro y generamos subtítulos dinámicos automáticamente."
        actions={
          <button type="button" onClick={fillGoldenPaths} className={btnSecondary}>
            <Sparkles className="h-3.5 w-3.5 text-amber-300" /> Probar con video de ejemplo
          </button>
        }
      />

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs sm:text-sm font-medium text-rose-200">
          {error}
        </div>
      )}

      {/* Top Grid: Create Session Form + Google Drive Status Panel */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_21rem]">
        {/* New Session Card */}
        <GlassCard as="form" onSubmit={handleCreateSession} className="space-y-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] pb-4">
            <div>
              <h2 className="text-base font-bold text-slate-50">Crear nueva sesión</h2>
              <p className="text-xs text-slate-400">
                Elige el origen de tus grabaciones de juego y cámara.
              </p>
            </div>
            <Segmented
              value={mode}
              onChange={setMode}
              options={[
                {
                  value: "local",
                  label: (
                    <>
                      <HardDrive className="h-3.5 w-3.5" /> En tu PC
                    </>
                  ),
                },
                {
                  value: "upload",
                  label: (
                    <>
                      <Upload className="h-3.5 w-3.5" /> Subir archivos
                    </>
                  ),
                },
                {
                  value: "drive",
                  label: (
                    <>
                      <FolderSync className="h-3.5 w-3.5" /> Google Drive
                    </>
                  ),
                },
              ]}
            />
          </div>

          <label className="block space-y-1.5">
            <span className="flex items-center gap-1 text-xs sm:text-sm font-semibold text-slate-200">
              ¿Qué jugaste en esta grabación?
              <InfoTip>
                Escribir el nombre del juego nos permite reconocer palabras propias de la partida (como armas, mapas o
                jugadas) para que los subtítulos salgan bien escritos.
              </InfoTip>
            </span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej. Valorant Ranked — partida con amigos"
              className={inputBase}
            />
            {keytermsInfo && (
              <span className="flex flex-wrap items-center gap-1.5 pt-0.5">
                {keytermsInfo.detected_game ? (
                  <Badge tone="success">
                    <Gamepad2 className="h-3 w-3" /> Vocabulario de{" "}
                    {keytermsInfo.detected_game.toUpperCase()} activado
                  </Badge>
                ) : (
                  <Badge>Vocabulario general de gaming</Badge>
                )}
                <InfoTip label="¿Por qué sirve esto?">
                  Reconoceremos automáticamente términos como{" "}
                  {keytermsInfo.resolved_keyterms.slice(0, 8).join(", ")}
                  {keytermsInfo.resolved_keyterms.length > 8 ? "…" : ""} para evitar errores en tus subtítulos.
                </InfoTip>
              </span>
            )}
          </label>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-[#0e1016] px-4 py-3">
            <div className="space-y-0.5">
              <span className="flex items-center gap-1 text-xs sm:text-sm font-semibold text-slate-200">
                ¿Cuántos clips quieres extraer?
                <InfoTip>
                  La IA seleccionará los mejores momentos hasta alcanzar este límite (entre 1 y 20 clips) y los renderizará automáticamente.
                </InfoTip>
              </span>
              <p className="text-[11px] text-slate-400">
                Elige un preset rápido o escribe la cantidad exacta (1–20).
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.02] p-1">
                {[3, 5, 8, 10].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setMaxClips(preset)}
                    className={`rounded-md px-2.5 py-1 font-mono text-xs font-semibold transition-colors cursor-pointer ${
                      maxClips === preset
                        ? "bg-amber-400/20 text-amber-200 border border-amber-400/40"
                        : "text-slate-400 hover:text-slate-200 border border-transparent"
                    }`}
                  >
                    {preset}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={1}
                  max={20}
                  step={1}
                  aria-label="Cantidad exacta de clips a extraer"
                  value={maxClips}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!Number.isNaN(val)) {
                      setMaxClips(Math.max(1, Math.min(20, val)));
                    }
                  }}
                  className={`${inputBase} w-20 text-center font-mono text-xs font-bold text-amber-300`}
                />
                <span className="text-xs text-slate-400">clips</span>
              </div>
            </div>
          </div>

          {mode === "local" ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block space-y-1.5">
                <span className="flex items-center gap-1 text-xs sm:text-sm font-semibold text-slate-200">
                  Video del juego
                  <InfoTip>
                    La grabación de tu pantalla (horizontal) donde se ven las jugadas y se oye el juego.
                  </InfoTip>
                </span>
                <input
                  type="text"
                  value={gameplayPath}
                  onChange={(e) => setGameplayPath(e.target.value)}
                  placeholder="C:\Grabaciones\sesion_01\gameplay.mp4"
                  className={`${inputBase} font-mono text-xs`}
                />
              </label>
              <label className="block space-y-1.5">
                <span className="flex items-center gap-1 text-xs sm:text-sm font-semibold text-slate-200">
                  Video de tu cámara
                  <InfoTip>
                    La grabación de tu webcam con tu voz para destacar tus reacciones arriba del juego.
                  </InfoTip>
                </span>
                <input
                  type="text"
                  value={cameraPath}
                  onChange={(e) => setCameraPath(e.target.value)}
                  placeholder="C:\Grabaciones\sesion_01\camara.mp4"
                  className={`${inputBase} font-mono text-xs`}
                />
              </label>
            </div>
          ) : mode === "upload" ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FilePick
                label="Video del juego (Gameplay)"
                hint="Haz clic para elegir gameplay.mp4"
                file={gameplayFile}
                onPick={setGameplayFile}
              />
              <FilePick
                label="Video de tu cámara (Facecam)"
                hint="Haz clic para elegir camara.mp4"
                file={cameraFile}
                onPick={setCameraFile}
              />
            </div>
          ) : (
            <div className="ax-card-muted space-y-3.5 p-4">
              {/* Drive Explorer Toolbar & Breadcrumbs */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
                <div className="flex flex-wrap items-center gap-1 text-xs font-medium text-slate-300">
                  {(driveBrowser?.breadcrumbs ?? [{ id: "root", name: "Drive" }]).map(
                    (bc, idx, arr) => (
                      <React.Fragment key={bc.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setDriveSearch("");
                            setDriveFolderId(bc.id);
                          }}
                          className={`rounded-md px-2 py-1 transition cursor-pointer ${
                            idx === arr.length - 1
                              ? "bg-amber-400/15 font-semibold text-amber-300"
                              : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100"
                          }`}
                        >
                          {bc.name}
                        </button>
                        {idx < arr.length - 1 && (
                          <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
                        )}
                      </React.Fragment>
                    )
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                    <input
                      type="text"
                      value={driveSearch}
                      onChange={(e) => setDriveSearch(e.target.value)}
                      placeholder="Filtrar carpeta o video…"
                      className="w-48 rounded-lg border border-white/[0.09] bg-[#0b0d11] py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-amber-400/60 focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => loadDriveFolder(driveFolderId, driveSearch)}
                    disabled={loadingDriveFiles}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.09] bg-white/[0.04] text-slate-300 transition hover:bg-white/[0.08] cursor-pointer"
                    title="Actualizar carpeta"
                  >
                    <RefreshCw
                      className={`h-3.5 w-3.5 ${loadingDriveFiles ? "animate-spin" : ""}`}
                    />
                  </button>
                </div>
              </div>

              {/* OAuth Connection Prompt if disconnected */}
              {drive?.mode === "oauth" && !drive.oauth_connected && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3.5 py-2.5 text-xs text-amber-200">
                  <span>Tu cuenta de Google Drive OAuth 2.0 aún no está vinculada.</span>
                  <div className="flex items-center gap-2">
                    {drive.client_configured ? (
                      <button
                        type="button"
                        onClick={handleConnectDriveOAuth}
                        className={`${btnPrimary} !px-3 !py-1.5 !text-xs`}
                      >
                        <Link2 className="h-3.5 w-3.5" /> Conectar Google Drive
                      </button>
                    ) : (
                      <Link
                        href="/settings"
                        className={`${btnSecondary} !px-3 !py-1.5 !text-xs`}
                      >
                        Configurar Client ID en Ajustes
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {driveBrowserError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-xs font-medium text-rose-200">
                  {driveBrowserError}
                </div>
              )}

              {/* 1-Click Auto-detected Pair Banner */}
              {driveBrowser?.detected_pair && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3.5 py-2">
                  <div className="min-w-0 text-xs text-emerald-100">
                    <span className="font-semibold text-emerald-300">
                      Par detectado automáticamente:
                    </span>{" "}
                    <span className="font-mono">{driveBrowser.detected_pair.gameplay.name}</span> +{" "}
                    <span className="font-mono">{driveBrowser.detected_pair.camera.name}</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleSelectDetectedPair}
                    className="inline-flex items-center gap-1.5 rounded-md bg-emerald-400 px-2.5 py-1 text-xs font-semibold text-slate-950 transition hover:bg-emerald-300 cursor-pointer"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> Elegir par en 1 clic
                  </button>
                </div>
              )}

              {/* Finder-Style Dense Rows for Folders & Videos */}
              <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
                {loadingDriveFiles ? (
                  <div className="flex items-center justify-center gap-2 py-8 text-xs text-slate-400">
                    <SoftSpinner className="h-4 w-4" /> Explorando Google Drive…
                  </div>
                ) : (
                  <>
                    {(driveBrowser?.folders ?? []).map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => {
                          setDriveSearch("");
                          setDriveFolderId(f.id);
                        }}
                        className="ax-row flex w-full items-center justify-between px-3 py-2 text-left text-xs cursor-pointer"
                      >
                        <span className="flex items-center gap-2 font-semibold text-slate-200">
                          <Folder className="h-4 w-4 text-amber-300" />
                          {f.name}
                        </span>
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400">
                          Abrir <ChevronRight className="h-3.5 w-3.5" />
                        </span>
                      </button>
                    ))}

                    {(driveBrowser?.files ?? []).map((v) => {
                      const isGp = driveGameplay?.id === v.id;
                      const isCam = driveCamera?.id === v.id;
                      return (
                        <div
                          key={v.id}
                          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition ${
                            isGp || isCam
                              ? "border-amber-400/40 bg-amber-400/[0.08]"
                              : "border-white/[0.06] bg-[#141720] hover:border-white/[0.14]"
                          }`}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <Film className="h-3.5 w-3.5 shrink-0 text-sky-300" />
                            <span className="truncate font-mono font-medium text-slate-100">
                              {v.name}
                            </span>
                            <span className="shrink-0 font-mono text-[11px] text-slate-500 tabular-nums">
                              {formatBytes(v.size)}
                            </span>
                            {v.role_hint === "gameplay" && (
                              <Badge tone="info">Juego sugerido</Badge>
                            )}
                            {v.role_hint === "camera" && (
                              <Badge tone="gold">Cámara sugerida</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setDriveGameplay(isGp ? null : v)}
                              className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-semibold transition cursor-pointer ${
                                isGp
                                  ? "bg-amber-400 text-slate-950"
                                  : "border border-white/[0.09] bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]"
                              }`}
                            >
                              <Gamepad2 className="h-3 w-3" />{" "}
                              {isGp ? "Juego ✓" : "Usar como Juego"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setDriveCamera(isCam ? null : v)}
                              className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-semibold transition cursor-pointer ${
                                isCam
                                  ? "bg-emerald-400 text-slate-950"
                                  : "border border-white/[0.09] bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]"
                              }`}
                            >
                              <Camera className="h-3 w-3" />{" "}
                              {isCam ? "Cámara ✓" : "Usar como Cámara"}
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {(driveBrowser?.folders.length ?? 0) === 0 &&
                      (driveBrowser?.files.length ?? 0) === 0 && (
                        <p className="py-6 text-center text-xs text-slate-500">
                          No hay subcarpetas ni archivos de video en esta ubicación.
                        </p>
                      )}
                  </>
                )}
              </div>

              {/* Selected Gameplay + Camera Summary */}
              <div className="grid grid-cols-1 gap-2.5 border-t border-white/[0.06] pt-3 md:grid-cols-2">
                <div className="rounded-lg border border-white/[0.07] bg-[#0b0d11] px-3 py-2 text-xs">
                  <div className="text-[11px] font-semibold text-slate-400">
                    Video del juego (Gameplay)
                  </div>
                  <div className="mt-0.5 truncate font-mono text-slate-100 tabular-nums">
                    {driveGameplay
                      ? `${driveGameplay.name} (${formatBytes(driveGameplay.size)})`
                      : "Sin seleccionar"}
                  </div>
                </div>
                <div className="rounded-lg border border-white/[0.07] bg-[#0b0d11] px-3 py-2 text-xs">
                  <div className="text-[11px] font-semibold text-slate-400">
                    Video de la cámara (Facecam)
                  </div>
                  <div className="mt-0.5 truncate font-mono text-slate-100 tabular-nums">
                    {driveCamera
                      ? `${driveCamera.name} (${formatBytes(driveCamera.size)})`
                      : "Sin seleccionar"}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
            <span className="flex items-center gap-1 text-xs text-slate-400">
              Formato vertical dinámico (9:16 · 1080×1920 · −14 LUFS)
              <InfoTip>
                Los 5 mejores momentos se preparan solos con tu cámara arriba, el juego abajo y subtítulos animados.
              </InfoTip>
            </span>
            <button type="submit" disabled={submitting} className={btnPrimary}>
              {submitting ? (
                <SoftSpinner onAccent className="h-4 w-4" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-current" />
              )}
              {mode === "drive" ? "Descargar de Drive y buscar clips" : "Buscar mejores clips"}
            </button>
          </div>
        </GlassCard>

        {/* Google Drive Sync Widget Card */}
        <GlassCard className="flex flex-col justify-between gap-5 p-5 sm:p-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-base font-bold text-slate-50">
                <FolderSync className="h-4 w-4 text-amber-300" /> Google Drive
              </h2>
              <div className="flex items-center gap-1.5">
                {drive && (
                  <Badge tone={drive.connected ? "success" : "neutral"}>
                    <StatusDot tone={drive.connected ? "online" : "neutral"} />
                    {drive.mode === "oauth"
                      ? drive.oauth_connected
                        ? "Conectada"
                        : "Sin vincular"
                      : drive.mode === "local"
                        ? "Carpeta local"
                        : drive.mode}
                  </Badge>
                )}
                <InfoTip label="¿Para qué sirve conectar Drive?" align="end">
                  Te permite elegir tus grabaciones guardadas en la nube sin descargarlas a mano y recibir los clips
                  terminados automáticamente en tu carpeta de Salidas.
                  {drive?.user_email ? ` · Cuenta: ${drive.user_email}` : ""}
                </InfoTip>
              </div>
            </div>
            <p className="text-xs leading-relaxed text-slate-400">
              {drive?.user_email
                ? `Conectado con ${drive.user_email}. Explora tus carpetas o deja tus grabaciones en Entradas para procesarlas solas.`
                : "Selecciona tus videos directo desde la nube o deja tus grabaciones en la carpeta Entradas."}
            </p>
            {drive && (
              <div className="grid grid-cols-2 gap-2.5">
                <div className="rounded-lg border border-white/[0.06] bg-[#0e1016] p-3 text-center">
                  <div className="font-mono text-2xl font-bold text-slate-50 tabular-nums">
                    {drive.entradas.length}
                  </div>
                  <div className="mt-0.5 text-[11px] font-medium text-slate-400">Por procesar</div>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-[#0e1016] p-3 text-center">
                  <div className="font-mono text-2xl font-bold text-emerald-300 tabular-nums">
                    {drive.salidas.length}
                  </div>
                  <div className="mt-0.5 text-[11px] font-medium text-slate-400">
                    Clips entregados
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="space-y-2 border-t border-white/[0.06] pt-4">
            <button
              type="button"
              onClick={() => setMode("drive")}
              className={`${btnPrimary} w-full`}
            >
              <Folder className="h-3.5 w-3.5" />
              Explorar carpetas de Drive
            </button>
            <button
              type="button"
              onClick={handlePollDrive}
              disabled={pollingDrive}
              className={`${btnSecondary} w-full`}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${pollingDrive ? "animate-spin" : ""}`} />
              Buscar grabaciones nuevas
            </button>
          </div>
        </GlassCard>
      </div>

      {/* Sessions Section with Astryx Filter & Search Toolbar */}
      <section className="space-y-4" aria-label="Sesiones">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-50">Tus sesiones</h2>
            <p className="text-xs text-slate-400">
              <span className="font-mono text-slate-200 tabular-nums">{sessions.length}</span>{" "}
              {sessions.length === 1 ? "grabación registrada" : "grabaciones registradas"}
              {activeCount > 0 ? ` · ${activeCount} en proceso ahora mismo` : ""}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {sessions.length > 0 && (
              <>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    value={sessionQuery}
                    onChange={(e) => setSessionQuery(e.target.value)}
                    placeholder="Buscar sesión o juego…"
                    className="w-44 sm:w-52 rounded-lg border border-white/[0.09] bg-[#0e1016] py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-amber-400/60 focus:outline-none"
                  />
                </div>
                <Segmented
                  value={sessionFilter}
                  onChange={setSessionFilter}
                  options={[
                    { value: "all", label: `Todas (${sessions.length})` },
                    { value: "running", label: `En curso (${activeCount})` },
                    { value: "delivered", label: `Listas (${deliveredCount})` },
                    ...(failedCount > 0
                      ? [{ value: "failed" as const, label: `Con aviso (${failedCount})` }]
                      : []),
                  ]}
                />
              </>
            )}

            <button type="button" onClick={reload} className={btnGhost}>
              <RefreshCw className="h-3.5 w-3.5" /> Actualizar
            </button>
          </div>
        </div>

        {loading ? (
          <div className="grid gap-3.5 xl:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-xl border border-white/[0.05] bg-[#161922] motion-reduce:animate-none"
              />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <EmptyState
            icon={<Gamepad2 className="h-5 w-5 text-amber-300" />}
            title="Aún no tienes sesiones registradas"
            description="Selecciona tus videos de juego y cámara arriba para iniciar el análisis automático o carga nuestra grabación de demostración."
            action={
              <button type="button" onClick={fillGoldenPaths} className={btnSecondary}>
                <Sparkles className="h-3.5 w-3.5 text-amber-300" /> Cargar grabación de ejemplo
              </button>
            }
          />
        ) : filteredSessions.length === 0 ? (
          <EmptyState
            icon={<Search className="h-5 w-5 text-slate-400" />}
            title="Ninguna sesión coincide con tu filtro"
            description="Prueba con otro término de búsqueda o vuelve a mostrar todas las grabaciones."
            action={
              <button
                type="button"
                onClick={() => {
                  setSessionFilter("all");
                  setSessionQuery("");
                }}
                className={btnSecondary}
              >
                Mostrar todas las sesiones
              </button>
            }
          />
        ) : (
          <div className="grid gap-3.5 xl:grid-cols-2">
            {filteredSessions.map((s) => {
              const steps = sessionSteps(s);
              return (
                <Link
                  key={s.id}
                  href={`/sessions/${s.id}`}
                  className="block rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
                >
                  <GlassCard interactive className="space-y-3.5 p-4 sm:p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm sm:text-base font-bold text-slate-50">
                            {s.title}
                          </span>
                          {s.detected_game && (
                            <Badge tone="info">
                              <Gamepad2 className="h-3 w-3" /> {s.detected_game.toUpperCase()}
                            </Badge>
                          )}
                        </div>
                        <p className="flex items-center gap-1.5 font-mono text-[11px] text-slate-400 tabular-nums">
                          <Clock className="h-3 w-3 text-slate-500" />{" "}
                          {new Date(s.created_at * 1000).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {stateBadge(s.state)}
                        <ChevronRight className="h-4 w-4 text-slate-500" />
                      </div>
                    </div>

                    <StepProgress
                      steps={PIPELINE_STEPS}
                      statuses={steps.statuses}
                      fill={steps.fill}
                      current={steps.current}
                      compact
                    />

                    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.05] pt-2.5 text-xs">
                      <span className="min-w-0 truncate text-slate-400">
                        {s.error ? (
                          <span className="text-rose-300">{s.error}</span>
                        ) : liveMessages[s.id] && steps.running ? (
                          <span className="text-amber-200">{liveMessages[s.id]}</span>
                        ) : (
                          <span>
                            <strong className="font-mono text-slate-200 tabular-nums">
                              {s.clips_count}
                            </strong>{" "}
                            momentos encontrados ·{" "}
                            <strong className="font-mono text-slate-200 tabular-nums">
                              {s.rendered_count}
                            </strong>{" "}
                            videos listos
                          </span>
                        )}
                      </span>
                      <span
                        className="flex items-center gap-1 text-[11px] text-slate-500"
                        onClick={(e) => e.preventDefault()}
                      >
                        Info
                        <InfoTip label="Resumen de la sesión" align="end">
                          Código: <span className="font-mono">{s.id}</span>
                          {s.sync && (
                            <>
                              <br />
                              Audio alineado automáticamente ({s.sync.shift_sec >= 0 ? "+" : ""}
                              {s.sync.shift_sec.toFixed(2)} s)
                            </>
                          )}
                        </InfoTip>
                      </span>
                    </div>
                  </GlassCard>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* Maintenance & Webhooks (Progressive Disclosure) */}
      <GlassCard as="section" className="p-5 sm:p-6">
        <Disclosure
          icon={<Wrench className="h-4 w-4" />}
          title="Espacio en disco y avisos automáticos"
          subtitle={
            maint
              ? `Archivos temporales: ${formatBytes(maint.temp_media_bytes)} · limpieza automática cada ${maint.temp_ttl_days} días`
              : "Liberar espacio y recibir avisos en Discord o Slack"
          }
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-3.5">
              <h3 className="flex items-center gap-1.5 text-xs sm:text-sm font-bold text-slate-200">
                <Trash2 className="h-4 w-4 text-slate-400" /> Liberar espacio en tu PC
                <InfoTip>
                  Borra pistas de audio intermedias que ya no se necesitan en sesiones terminadas, pero conserva tus
                  videos finales y los análisis guardados para que nunca pagues dos veces por la misma grabación.
                </InfoTip>
              </h3>
              {maint && (
                <DetailList
                  items={[
                    ["Pistas temporales borrables", formatBytes(maint.temp_media_bytes)],
                    ["Videos terminados (MP4)", formatBytes(maint.renders_bytes)],
                    ["Análisis guardados (ahorro)", formatBytes(maint.preserved_cache_bytes)],
                    ["Limpieza automática", `Cada ${maint.temp_ttl_days ?? 7} días`],
                  ]}
                />
              )}
              <button
                type="button"
                onClick={handleCleanupNow}
                disabled={cleaningUp}
                className={btnSecondary}
              >
                {cleaningUp ? (
                  <SoftSpinner className="h-3.5 w-3.5" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                Liberar espacio ahora
              </button>
            </div>

            <div className="space-y-3.5">
              <h3 className="flex items-center gap-1.5 text-xs sm:text-sm font-bold text-slate-200">
                <Bell className="h-4 w-4 text-slate-400" /> Avisos en Discord o Slack
                <InfoTip>
                  Recibe un mensaje automático en tu servidor de Discord o Slack apenas tus clips estén listos para ver y
                  descargar.
                </InfoTip>
              </h3>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={webhookUrlInput}
                  onChange={(e) => setWebhookUrlInput(e.target.value)}
                  placeholder="https://discord.com/api/webhooks/…"
                  className={`${inputBase} min-w-0 flex-1 font-mono text-xs`}
                />
                <button
                  type="button"
                  onClick={handleTestWebhook}
                  disabled={testingWebhook}
                  className={`${btnSecondary} shrink-0`}
                >
                  {testingWebhook ? (
                    <SoftSpinner className="h-3.5 w-3.5" />
                  ) : (
                    <Bell className="h-3.5 w-3.5" />
                  )}
                  Enviar prueba
                </button>
              </div>
            </div>
          </div>
          {maintMsg && (
            <p className="mt-4 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-3.5 py-2 text-xs font-medium text-emerald-200">
              {maintMsg}
            </p>
          )}
        </Disclosure>
      </GlassCard>
    </div>
  );
}
