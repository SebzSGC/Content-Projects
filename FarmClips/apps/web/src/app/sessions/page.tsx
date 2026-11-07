"use client";

import React, { useCallback, useEffect, useState } from "react";
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
  GlassCard,
  InfoTip,
  Segmented,
  SoftSpinner,
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

function FilePick({ label, file, onPick }: { label: string; file: File | null; onPick: (f: File | null) => void }) {
  return (
    <label className="group flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border border-dashed border-white/15 bg-slate-900/50 p-5 text-center transition-all duration-300 hover:scale-[1.01] hover:border-amber-300/40 hover:bg-slate-900/80">
      <Upload className="h-5 w-5 text-slate-500 transition-colors duration-300 group-hover:text-amber-300" />
      <span className="text-sm font-bold text-slate-200">{label}</span>
      <span className="max-w-full truncate text-xs text-slate-400">{file ? file.name : "Haz clic para elegir el archivo"}</span>
      <input type="file" accept="video/*" className="hidden" onChange={(e) => onPick(e.target.files?.[0] ?? null)} />
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

  // Form state
  const [mode, setMode] = useState<"local" | "upload" | "drive">("local");
  const [title, setTitle] = useState("");
  const [gameplayPath, setGameplayPath] = useState("");
  const [cameraPath, setCameraPath] = useState("");
  const [gameplayFile, setGameplayFile] = useState<File | null>(null);
  const [cameraFile, setCameraFile] = useState<File | null>(null);
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

  const loadDriveFolder = useCallback(
    async (folderId?: string, query?: string) => {
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
              : res.detected_pair?.recording_name && res.detected_pair.recording_name !== "Raíz local" && res.detected_pair.recording_name !== "Mi unidad"
              ? res.detected_pair.recording_name
              : prev
          );
        }
      } catch (err) {
        setDriveBrowserError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingDriveFiles(false);
      }
    },
    []
  );

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
          throw new Error("Selecciona los videos de Juego (gameplay) y Cámara desde el explorador de Google Drive.");
        }
        if (gp.id === cm.id) {
          throw new Error("El video de gameplay y el de cámara deben ser archivos distintos.");
        }
        const recName = title.trim() || driveBrowser?.folder_name || "Sesión Drive";
        const created = await createDriveSession({
          title: recName,
          folder_id: driveBrowser?.folder_id,
          gameplay_file_id: gp.id,
          camera_file_id: cm.id,
          recording_name: recName,
          language: "es",
          style_preset: "hormozi-gaming",
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
        const [upGp, upCm] = await Promise.all([uploadVideoFile(gameplayFile), uploadVideoFile(cameraFile)]);
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

  const activeCount = sessions.filter((s) => sessionSteps(s).running).length;

  return (
    <div className="space-y-8">
      {/* Header ------------------------------------------------------------ */}
      <header className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-2 inline-flex items-center gap-2 rounded-full bg-amber-400/10 px-3 py-1 text-xs font-bold text-amber-300">
            <Gamepad2 className="h-3.5 w-3.5" /> Estudio de clips
          </p>
          <h1 className="flex items-center gap-2 text-3xl font-black tracking-tight text-slate-50 sm:text-4xl">
            Tus grabaciones, en Shorts
            <InfoTip label="Cómo funciona">
              Solo viaja a la nube audio Opus mono 16 kHz (~7 MB/h) y texto compacto. El video se queda en tu equipo:
              sincronización FFT, tracking facial MediaPipe por clip, EditPlan v2 y render 1080×1920 a −14 LUFS.
            </InfoTip>
          </h1>
          <p className="mt-2 max-w-xl text-base text-slate-400">
            Juego y cámara por separado entran; salen los mejores momentos listos para publicar.
          </p>
        </div>
        <button type="button" onClick={fillGoldenPaths} className={btnSecondary}>
          <Sparkles className="h-4 w-4 text-amber-300" /> Cargar grabación de prueba
        </button>
      </header>

      {error && (
        <div className="rounded-3xl border border-rose-400/20 bg-rose-500/10 px-5 py-3 text-sm font-semibold text-rose-200">{error}</div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* New session ----------------------------------------------------- */}
        <GlassCard as="form" onSubmit={handleCreateSession} className="space-y-5 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-extrabold text-slate-50">Nueva sesión</h2>
            <Segmented
              value={mode}
              onChange={setMode}
              options={[
                { value: "local", label: <><HardDrive className="h-3.5 w-3.5" /> Rutas locales</> },
                { value: "upload", label: <><Upload className="h-3.5 w-3.5" /> Subir archivos</> },
                { value: "drive", label: <><FolderSync className="h-3.5 w-3.5" /> Desde Drive</> },
              ]}
            />
          </div>

          <label className="block space-y-2">
            <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
              Nombre o juego de la grabación
              <InfoTip>Ayuda a la transcripción (keyterms de Deepgram Nova-3) y a la IA que elige los momentos.</InfoTip>
            </span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej. Valorant Ranked — sesión de noche"
              className={inputBase}
            />
            {keytermsInfo && (
              <span className="flex flex-wrap items-center gap-1.5">
                {keytermsInfo.detected_game ? (
                  <Badge tone="success">
                    <Gamepad2 className="h-3 w-3" /> Juego detectado: {keytermsInfo.detected_game.toUpperCase()}
                  </Badge>
                ) : (
                  <Badge>Vocabulario general de gaming</Badge>
                )}
                <InfoTip label="Palabras clave">
                  {keytermsInfo.resolved_keyterms.length} palabras clave para la transcripción:{" "}
                  {keytermsInfo.resolved_keyterms.slice(0, 12).join(", ")}
                  {keytermsInfo.resolved_keyterms.length > 12 ? "…" : ""}
                  {!keytermsInfo.detected_game && " · Escribe el juego (Valorant, LoL, CS2, Fortnite…) para afinarla."}
                </InfoTip>
              </span>
            )}
          </label>

          {mode === "local" ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block space-y-2">
                <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
                  Video del juego
                  <InfoTip>gameplay.mp4 en 16:9, con el audio del juego o la mezcla.</InfoTip>
                </span>
                <input
                  type="text"
                  value={gameplayPath}
                  onChange={(e) => setGameplayPath(e.target.value)}
                  placeholder="C:\Grabaciones\sesion_01\gameplay.mp4"
                  className={`${inputBase} font-mono text-xs`}
                />
              </label>
              <label className="block space-y-2">
                <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
                  Video de la cámara
                  <InfoTip>camara.mp4 con tu rostro y el micrófono limpio.</InfoTip>
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
              <FilePick label="Video del juego" file={gameplayFile} onPick={setGameplayFile} />
              <FilePick label="Video de la cámara" file={cameraFile} onPick={setCameraFile} />
            </div>
          ) : (
            <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-4">
              {/* Drive Explorer Header & Breadcrumbs */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1 text-xs font-semibold text-slate-300">
                  {(driveBrowser?.breadcrumbs ?? [{ id: "root", name: "Drive" }]).map((bc, idx, arr) => (
                    <React.Fragment key={bc.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setDriveSearch("");
                          setDriveFolderId(bc.id);
                        }}
                        className={`rounded-lg px-2 py-1 transition cursor-pointer ${
                          idx === arr.length - 1
                            ? "bg-amber-400/15 font-extrabold text-amber-300"
                            : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                        }`}
                      >
                        {bc.name}
                      </button>
                      {idx < arr.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-slate-600" />}
                    </React.Fragment>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                    <input
                      type="text"
                      value={driveSearch}
                      onChange={(e) => setDriveSearch(e.target.value)}
                      placeholder="Buscar carpeta o video…"
                      className="w-44 rounded-full border border-white/10 bg-slate-950/70 py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-amber-300/60 focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => loadDriveFolder(driveFolderId, driveSearch)}
                    disabled={loadingDriveFiles}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-300 transition hover:bg-white/10 cursor-pointer"
                    title="Actualizar carpeta"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${loadingDriveFiles ? "animate-spin" : ""}`} />
                  </button>
                </div>
              </div>

              {/* OAuth Connection Prompt if disconnected */}
              {drive?.mode === "oauth" && !drive.oauth_connected && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-xs text-amber-200">
                  <span>Tu cuenta de Google Drive OAuth 2.0 aún no está vinculada.</span>
                  <div className="flex items-center gap-2">
                    {drive.client_configured ? (
                      <button type="button" onClick={handleConnectDriveOAuth} className={`${btnPrimary} !px-3.5 !py-1.5 !text-xs`}>
                        <Link2 className="h-3.5 w-3.5" /> Conectar Google Drive
                      </button>
                    ) : (
                      <Link href="/settings" className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}>
                        Configurar Client ID en Ajustes
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {driveBrowserError && (
                <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-2.5 text-xs font-semibold text-rose-200">
                  {driveBrowserError}
                </div>
              )}

              {/* 1-Click Auto-detected Pair Banner */}
              {driveBrowser?.detected_pair && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-2.5">
                  <div className="min-w-0 text-xs text-emerald-100">
                    <span className="font-extrabold text-emerald-300">Par detectado automáticamente:</span>{" "}
                    <span className="font-mono">{driveBrowser.detected_pair.gameplay.name}</span> +{" "}
                    <span className="font-mono">{driveBrowser.detected_pair.camera.name}</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleSelectDetectedPair}
                    className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400 px-3 py-1 text-xs font-extrabold text-slate-950 transition hover:bg-emerald-300 cursor-pointer"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> Elegir par en 1 clic
                  </button>
                </div>
              )}

              {/* Folders & Videos list */}
              <div className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
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
                        className="flex w-full items-center justify-between rounded-xl border border-white/5 bg-slate-950/50 px-3.5 py-2 text-left text-xs transition hover:border-amber-300/30 hover:bg-slate-900 cursor-pointer"
                      >
                        <span className="flex items-center gap-2 font-bold text-slate-200">
                          <Folder className="h-4 w-4 text-amber-300" />
                          {f.name}
                        </span>
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400">
                          Abrir carpeta <ChevronRight className="h-3.5 w-3.5" />
                        </span>
                      </button>
                    ))}

                    {(driveBrowser?.files ?? []).map((v) => {
                      const isGp = driveGameplay?.id === v.id;
                      const isCam = driveCamera?.id === v.id;
                      return (
                        <div
                          key={v.id}
                          className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3.5 py-2 text-xs transition ${
                            isGp || isCam
                              ? "border-amber-300/40 bg-amber-400/10"
                              : "border-white/5 bg-slate-950/40 hover:border-white/15"
                          }`}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <Film className="h-4 w-4 shrink-0 text-sky-300" />
                            <span className="truncate font-mono font-semibold text-slate-100">{v.name}</span>
                            <span className="shrink-0 text-[11px] text-slate-400">({formatBytes(v.size)})</span>
                            {v.role_hint === "gameplay" && <Badge tone="info">Juego sugerido</Badge>}
                            {v.role_hint === "camera" && <Badge tone="gold">Cámara sugerida</Badge>}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setDriveGameplay(isGp ? null : v)}
                              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold transition cursor-pointer ${
                                isGp
                                  ? "bg-amber-400 text-slate-950"
                                  : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
                              }`}
                            >
                              <Gamepad2 className="h-3 w-3" /> {isGp ? "Juego ✓" : "Usar como Juego"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setDriveCamera(isCam ? null : v)}
                              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold transition cursor-pointer ${
                                isCam
                                  ? "bg-emerald-400 text-slate-950"
                                  : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
                              }`}
                            >
                              <Camera className="h-3 w-3" /> {isCam ? "Cámara ✓" : "Usar como Cámara"}
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {(driveBrowser?.folders.length ?? 0) === 0 && (driveBrowser?.files.length ?? 0) === 0 && (
                      <p className="py-6 text-center text-xs text-slate-400">
                        No hay subcarpetas ni archivos de video en esta ubicación.
                      </p>
                    )}
                  </>
                )}
              </div>

              {/* Selected Gameplay + Camera Summary */}
              <div className="grid grid-cols-1 gap-3 border-t border-white/10 pt-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-slate-950/60 px-3.5 py-2.5 text-xs">
                  <div className="font-bold text-slate-400">Video del juego (Gameplay)</div>
                  <div className="mt-0.5 truncate font-mono text-slate-100">
                    {driveGameplay ? `${driveGameplay.name} (${formatBytes(driveGameplay.size)})` : "Sin seleccionar"}
                  </div>
                </div>
                <div className="rounded-xl border border-white/10 bg-slate-950/60 px-3.5 py-2.5 text-xs">
                  <div className="font-bold text-slate-400">Video de la cámara (Facecam)</div>
                  <div className="mt-0.5 truncate font-mono text-slate-100">
                    {driveCamera ? `${driveCamera.name} (${formatBytes(driveCamera.size)})` : "Sin seleccionar"}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <span className="flex items-center gap-1 text-sm text-slate-400">
              Estilo Hormozi Gaming
              <InfoTip>Preset hormozi-gaming. Los 5 mejores clips con más de 60/100 se renderizan solos en 1080p.</InfoTip>
            </span>
            <button type="submit" disabled={submitting} className={btnPrimary}>
              {submitting ? <SoftSpinner onAccent className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
              {mode === "drive" ? "Descargar de Drive y crear clips" : "Crear clips"}
            </button>
          </div>
        </GlassCard>

        {/* Google Drive ---------------------------------------------------- */}
        <GlassCard className="flex flex-col justify-between gap-5 p-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-50">
                <FolderSync className="h-5 w-5 text-amber-300" /> Google Drive
              </h2>
              <div className="flex items-center gap-1.5">
                {drive && (
                  <Badge tone={drive.connected ? "success" : "neutral"}>
                    {drive.mode === "oauth"
                      ? drive.oauth_connected
                        ? "OAuth conectado"
                        : "OAuth sin vincular"
                      : drive.mode}
                  </Badge>
                )}
                <InfoTip label="Cómo funciona Drive" align="end">
                  Conecta tu cuenta por OAuth 2.0, Cuenta de Servicio o espejo local. Explora cualquier carpeta en la
                  pestaña &quot;Desde Drive&quot; o vigila Entradas/&lt;grabación&gt;/ automáticamente.
                  {drive?.user_email ? ` · Cuenta: ${drive.user_email}` : ""}
                </InfoTip>
              </div>
            </div>
            <p className="text-sm text-slate-400">
              {drive?.user_email
                ? `Conectado como ${drive.user_email}. Elige cualquier carpeta en el explorador o usa Entradas/ → Salidas/.`
                : "Elige videos directo desde el explorador interactivo de Drive o deja una carpeta en Entradas/."}
            </p>
            {drive && (
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-white/5 p-3 text-center">
                  <div className="text-2xl font-black text-slate-50">{drive.entradas.length}</div>
                  <div className="text-xs font-semibold text-slate-400">En Entradas</div>
                </div>
                <div className="rounded-2xl bg-white/5 p-3 text-center">
                  <div className="text-2xl font-black text-slate-50">{drive.salidas.length}</div>
                  <div className="text-xs font-semibold text-slate-400">Entregadas</div>
                </div>
              </div>
            )}
          </div>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setMode("drive")}
              className={`${btnPrimary} w-full`}
            >
              <Folder className="h-4 w-4" />
              Explorar carpetas de Drive
            </button>
            <button type="button" onClick={handlePollDrive} disabled={pollingDrive} className={`${btnSecondary} w-full`}>
              <RefreshCw className={`h-4 w-4 ${pollingDrive ? "animate-spin" : ""}`} />
              Revisar Entradas ahora
            </button>
          </div>
        </GlassCard>
      </div>

      {/* Sessions ------------------------------------------------------------ */}
      <section className="space-y-4" aria-label="Sesiones">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-black text-slate-50">Sesiones</h2>
            <p className="text-sm text-slate-400">
              {sessions.length} en total{activeCount > 0 ? ` · ${activeCount} en proceso` : ""}
            </p>
          </div>
          <button type="button" onClick={reload} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-slate-400 transition-all duration-300 hover:bg-white/5 hover:text-slate-100">
            <RefreshCw className="h-4 w-4" /> Actualizar
          </button>
        </div>

        {loading ? (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-3xl bg-slate-800/40 motion-reduce:animate-none" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <GlassCard className="flex flex-col items-center gap-3 p-12 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-amber-400/10">
              <Gamepad2 className="h-7 w-7 text-amber-300" />
            </span>
            <p className="text-lg font-extrabold text-slate-100">Todavía no hay sesiones</p>
            <p className="max-w-md text-sm text-slate-400">
              Crea una arriba, deja una carpeta con los dos videos en Entradas/ o{" "}
              <button type="button" onClick={fillGoldenPaths} className="font-bold text-amber-300 hover:text-amber-200">
                carga la grabación de prueba
              </button>
              .
            </p>
          </GlassCard>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {sessions.map((s) => {
              const steps = sessionSteps(s);
              return (
                <Link key={s.id} href={`/sessions/${s.id}`} className="block rounded-3xl focus:outline-none focus-visible:ring-4 focus-visible:ring-amber-400/30">
                  <GlassCard interactive className="space-y-4 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-base font-extrabold text-slate-50">{s.title}</span>
                          {s.detected_game && (
                            <Badge tone="info">
                              <Gamepad2 className="h-3 w-3" /> {s.detected_game.toUpperCase()}
                            </Badge>
                          )}
                        </div>
                        <p className="flex items-center gap-1.5 text-sm text-slate-400">
                          <Clock className="h-3.5 w-3.5" /> {new Date(s.created_at * 1000).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {stateBadge(s.state)}
                        <ChevronRight className="h-4 w-4 text-slate-500" />
                      </div>
                    </div>

                    <StepProgress steps={PIPELINE_STEPS} statuses={steps.statuses} fill={steps.fill} current={steps.current} compact />

                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span className="min-w-0 truncate text-slate-400">
                        {s.error ? (
                          <span className="text-rose-300">{s.error}</span>
                        ) : liveMessages[s.id] && steps.running ? (
                          liveMessages[s.id]
                        ) : (
                          `${s.clips_count} clips · ${s.rendered_count} listos en 1080p`
                        )}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-slate-500">
                        Detalles
                        <InfoTip label="Detalles técnicos de la sesión" align="end">
                          ID: <span className="font-mono">{s.id}</span>
                          <br />
                          Estado interno: {s.state}
                          {s.sync && (
                            <>
                              <br />
                              Sync: {s.sync.method} ({s.sync.shift_sec >= 0 ? "+" : ""}
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

      {/* Maintenance & webhooks (progressive disclosure) --------------------- */}
      <GlassCard as="section" className="p-6">
        <Disclosure
          icon={<Wrench className="h-5 w-5" />}
          title="Mantenimiento y notificaciones"
          subtitle={maint ? `Temporales: ${formatBytes(maint.temp_media_bytes)} · limpieza automática cada ${maint.temp_ttl_days} días` : "Limpieza de temporales y webhooks"}
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-slate-200">
                <Trash2 className="h-4 w-4 text-slate-400" /> Limpieza de temporales
                <InfoTip>
                  Borra los WAV/Opus intermedios de sesiones entregadas. Conserva Parquet, EditPlan, respuestas de la API y SQLite
                  (la caché que evita volver a pagar).
                </InfoTip>
              </h3>
              {maint && (
                <DetailList
                  items={[
                    ["WAV/Opus temporales", formatBytes(maint.temp_media_bytes)],
                    ["Renders MP4", formatBytes(maint.renders_bytes)],
                    ["Caché protegida", formatBytes(maint.preserved_cache_bytes)],
                    ["TTL automático", `${maint.temp_ttl_days ?? 7} días`],
                  ]}
                />
              )}
              <button type="button" onClick={handleCleanupNow} disabled={cleaningUp} className={btnSecondary}>
                {cleaningUp ? <SoftSpinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                Limpiar ahora
              </button>
            </div>

            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-slate-200">
                <Bell className="h-4 w-4 text-slate-400" /> Notificaciones (Discord / Slack / HTTP)
                <InfoTip>
                  Al terminar una sesión envía el resumen de los mejores clips con enlaces al editor.{" "}
                  {maint?.webhook_configured ? "CLIPS_WEBHOOK_URL está configurada." : "Puedes probar una URL aquí."}
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
                <button type="button" onClick={handleTestWebhook} disabled={testingWebhook} className={`${btnSecondary} shrink-0`}>
                  {testingWebhook ? <SoftSpinner className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
                  Probar
                </button>
              </div>
            </div>
          </div>
          {maintMsg && <p className="mt-4 rounded-2xl bg-emerald-400/10 px-4 py-2 text-sm font-semibold text-emerald-200">{maintMsg}</p>}
        </Disclosure>
      </GlassCard>
    </div>
  );
}
