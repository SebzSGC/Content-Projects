"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Cpu,
  DollarSign,
  Eye,
  EyeOff,
  FolderSync,
  KeyRound,
  Link2,
  Mic,
  RefreshCw,
  Save,
  ShieldCheck,
  Sliders,
  Sparkles,
  Unlink,
  Wifi,
} from "lucide-react";
import {
  type AppSettings,
  type BudgetSummary,
  type DriveStatus,
  type FilmCraftStatus,
  type TestConnectionResult,
  completeDriveAuthCallback,
  disconnectDriveAuth,
  fetchBudget,
  fetchDriveAuthUrl,
  fetchDriveStatus,
  fetchFilmCraftStatus,
  getSettings,
  saveSettings,
  testSettingsConnection,
} from "@/lib/api/client";
import {
  Badge,
  btnPrimary,
  btnSecondary,
  GlassCard,
  InfoTip,
  inputBase,
  ProgressBar,
  SoftSpinner,
} from "@/components/ui";

type ProviderId = "deepgram" | "groq" | "gemini" | "openai_compat" | "fixture";

const GEMINI_MODELS = [
  { value: "gemini-3.5-flash-lite", label: "gemini-3.5-flash-lite (Recomendado)" },
  { value: "gemini-3.8-flash", label: "gemini-3.8-flash (Alta capacidad)" },
];

const OPENAI_COMPAT_MODELS = [
  { value: "gpt-6-luna", label: "gpt-6-luna (Reemplazo oficial de gpt-4o-mini)" },
  { value: "gpt-4o-mini", label: "gpt-4o-mini (Auto-normalizado a gpt-6-luna)" },
  { value: "llama-3.3-70b-versatile", label: "llama-3.3-70b-versatile (Groq / OpenRouter)" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [budget, setBudget] = useState<BudgetSummary | null>(null);
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null);
  const [filmcraftStatus, setFilmcraftStatus] = useState<FilmCraftStatus | null>(null);
  const [checkingFilmcraft, setCheckingFilmcraft] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingDrive, setLoadingDrive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // Editable form state
  const [sttPrimary, setSttPrimary] = useState<"deepgram" | "groq" | "fixture">("deepgram");
  const [sttBackup, setSttBackup] = useState<"groq" | "deepgram" | "fixture" | "none">("groq");
  const [deepgramModel, setDeepgramModel] = useState("nova-3");
  const [groqSttModel, setGroqSttModel] = useState("whisper-large-v3-turbo");

  const [llmPrimary, setLlmPrimary] = useState<"gemini" | "openai_compat" | "fixture">("gemini");
  const [llmModel, setLlmModel] = useState("gemini-3.5-flash-lite");
  const [llmBackup, setLlmBackup] = useState<"openai_compat" | "gemini" | "fixture" | "none">("openai_compat");
  const [llmBackupModel, setLlmBackupModel] = useState("gpt-6-luna");
  const [llmBackupBaseUrl, setLlmBackupBaseUrl] = useState("https://api.openai.com/v1");

  const [maxBudgetUsd, setMaxBudgetUsd] = useState<number>(9.0);
  const [autoRenderTopK, setAutoRenderTopK] = useState<number>(5);
  const [webhookUrl, setWebhookUrl] = useState<string>("");
  const [tempTtlDays, setTempTtlDays] = useState<number>(7.0);

  // Google Drive OAuth 2.0 & Watcher state
  const [driveMode, setDriveMode] = useState<"local" | "oauth" | "service_account" | "disabled">("local");
  const [driveClientId, setDriveClientId] = useState("");
  const [driveClientSecret, setDriveClientSecret] = useState("");
  const [driveRootFolderId, setDriveRootFolderId] = useState("");
  const [driveLocalDir, setDriveLocalDir] = useState("");
  const [drivePollSec, setDrivePollSec] = useState<number>(120);
  const [driveAuthCode, setDriveAuthCode] = useState("");
  const [connectingDrive, setConnectingDrive] = useState(false);

  // API key inputs (kept blank unless the user types a new key; placeholder shows masked value)
  const [deepgramKey, setDeepgramKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");

  // Show/hide password toggles
  const [showKey, setShowKey] = useState<Record<string, boolean>>({
    deepgram: false,
    groq: false,
    gemini: false,
    openai: false,
    driveSecret: false,
  });

  // Per-provider test connection state
  const [testingProvider, setTestingProvider] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, TestConnectionResult>>({});
  const [activeSection, setActiveSection] = useState<
    "all" | "stt" | "llm" | "budget" | "drive" | "filmcraft"
  >("all");

  const showToast = useCallback((kind: "ok" | "err", text: string) => {
    setToast({ kind, text });
    setTimeout(() => {
      setToast((prev) => (prev?.text === text ? null : prev));
    }, 5000);
  }, []);

  const applyLoadedSettings = useCallback((s: AppSettings) => {
    setSettings(s);
    setSttPrimary(s.stt_primary);
    setSttBackup(s.stt_backup);
    setDeepgramModel(s.deepgram_model || "nova-3");
    setGroqSttModel(s.groq_stt_model || "whisper-large-v3-turbo");
    setLlmPrimary(s.llm_primary);
    setLlmModel(s.llm_model || "gemini-3.5-flash-lite");
    setLlmBackup(s.llm_backup);
    setLlmBackupModel(s.llm_backup_model || "gpt-6-luna");
    setLlmBackupBaseUrl(s.llm_backup_base_url || "https://api.openai.com/v1");
    setMaxBudgetUsd(s.max_budget_usd);
    setAutoRenderTopK(s.auto_render_top_k ?? 5);
    setWebhookUrl(s.webhook_url || "");
    setTempTtlDays(s.temp_ttl_days ?? 7.0);
    setDriveMode(s.drive_mode || "local");
    setDriveClientId(s.drive_client_id || "");
    setDriveRootFolderId(s.drive_root_folder_id || "");
    setDriveLocalDir(s.drive_local_dir || "");
    setDrivePollSec(s.drive_poll_sec ?? 120);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Cargar configuración principal y presupuesto de inmediato (< 5 ms)
      const [s, b] = await Promise.all([
        getSettings(),
        fetchBudget(),
      ]);
      applyLoadedSettings(s);
      setBudget(b);
      setLoading(false);

      // 2. Cargar diagnósticos externos en paralelo sin bloquear la pantalla
      setLoadingDrive(true);

      fetchDriveStatus()
        .then((d) => setDriveStatus(d))
        .catch(() => null)
        .finally(() => setLoadingDrive(false));

      fetchFilmCraftStatus()
        .then((fc) => setFilmcraftStatus(fc))
        .catch(() => null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la configuración del servidor.");
      setLoading(false);
    }
  }, [applyLoadedSettings]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      if (ev.data && typeof ev.data === "object" && ev.data.type === "drive_oauth_connected") {
        showToast("ok", "Cuenta de Google Drive vinculada por OAuth 2.0.");
        loadAll();
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [loadAll, showToast]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await saveSettings({
        stt_primary: sttPrimary,
        stt_backup: sttBackup,
        deepgram_model: deepgramModel.trim() || "nova-3",
        groq_stt_model: groqSttModel.trim() || "whisper-large-v3-turbo",
        llm_primary: llmPrimary,
        llm_model: llmModel.trim() || "gemini-3.5-flash-lite",
        llm_backup: llmBackup,
        llm_backup_model: llmBackupModel.trim() || "gpt-6-luna",
        llm_backup_base_url: llmBackupBaseUrl.trim() || "https://api.openai.com/v1",
        max_budget_usd: Number(maxBudgetUsd) || 9.0,
        auto_render_top_k: Math.max(1, Math.min(20, Math.round(Number(autoRenderTopK) || 5))),
        webhook_url: webhookUrl.trim(),
        temp_ttl_days: Number(tempTtlDays) >= 0 ? Number(tempTtlDays) : 7.0,
        drive_mode: driveMode,
        drive_client_id: driveClientId.trim(),
        drive_client_secret: driveClientSecret.trim() || undefined,
        drive_root_folder_id: driveRootFolderId.trim(),
        drive_local_dir: driveLocalDir.trim() || undefined,
        drive_poll_sec: Number(drivePollSec) >= 0 ? Number(drivePollSec) : 120,
        deepgram_api_key: deepgramKey.trim() || undefined,
        groq_api_key: groqKey.trim() || undefined,
        gemini_api_key: geminiKey.trim() || undefined,
        openai_api_key: openaiKey.trim() || undefined,
      });
      applyLoadedSettings(updated);
      setDeepgramKey("");
      setGroqKey("");
      setGeminiKey("");
      setOpenaiKey("");
      setDriveClientSecret("");

      const freshBudget = await fetchBudget().catch(() => null);
      if (freshBudget) setBudget(freshBudget);
      showToast("ok", "Configuración guardada en .env y aplicada en memoria.");

      // Refrescar diagnósticos externos en segundo plano
      fetchDriveStatus().then((d) => setDriveStatus(d)).catch(() => null);
      fetchFilmCraftStatus().then((fc) => setFilmcraftStatus(fc)).catch(() => null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al guardar la configuración";
      setError(msg);
      showToast("err", msg);
    } finally {
      setSaving(false);
    }
  };

  const handleCheckFilmcraft = async () => {
    setCheckingFilmcraft(true);
    try {
      const st = await fetchFilmCraftStatus();
      setFilmcraftStatus(st);
      showToast(
        st.installed ? "ok" : "err",
        st.installed
          ? `FilmCraft detectado (v${st.version || "0.20.1"}). Bridge: ${st.bridge_up ? "Conectado" : "Inactivo"}`
          : "No se encontró FilmCraft en el equipo."
      );
    } catch {
      showToast("err", "No se pudo consultar el estado de FilmCraft.");
    } finally {
      setCheckingFilmcraft(false);
    }
  };

  const handleStartDriveOAuth = async () => {
    setConnectingDrive(true);
    setError(null);
    try {
      // Save current Drive OAuth credentials first so the backend has Client ID & Secret
      const updated = await saveSettings({
        drive_mode: "oauth",
        drive_client_id: driveClientId.trim(),
        drive_client_secret: driveClientSecret.trim() || undefined,
        drive_root_folder_id: driveRootFolderId.trim(),
      });
      applyLoadedSettings(updated);
      setDriveClientSecret("");
      const res = await fetchDriveAuthUrl();
      window.open(res.auth_url, "_blank", "noopener,noreferrer,width=560,height=680");
      showToast("ok", "Ventana de autorización de Google Drive abierta.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "No se pudo iniciar OAuth 2.0 con Google Drive.";
      setError(msg);
      showToast("err", msg);
    } finally {
      setConnectingDrive(false);
    }
  };

  const handleExchangeDriveCode = async () => {
    if (!driveAuthCode.trim()) return;
    setConnectingDrive(true);
    setError(null);
    try {
      await completeDriveAuthCallback(driveAuthCode.trim());
      setDriveAuthCode("");
      await loadAll();
      showToast("ok", "Google Drive conectado y token guardado en data/drive_oauth_token.json.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al canjear código OAuth de Google Drive.";
      setError(msg);
      showToast("err", msg);
    } finally {
      setConnectingDrive(false);
    }
  };

  const handleDisconnectDrive = async () => {
    setConnectingDrive(true);
    setError(null);
    try {
      await disconnectDriveAuth();
      await loadAll();
      showToast("ok", "Cuenta de Google Drive desconectada.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al desconectar Google Drive.";
      setError(msg);
      showToast("err", msg);
    } finally {
      setConnectingDrive(false);
    }
  };

  const handleTestConnection = async (provider: ProviderId) => {
    setTestingProvider((prev) => ({ ...prev, [provider]: true }));
    try {
      let keyToSend: string | undefined;
      let modelToSend: string | undefined;
      let baseUrlToSend: string | undefined;

      if (provider === "deepgram") {
        keyToSend = deepgramKey.trim() || undefined;
        modelToSend = deepgramModel;
      } else if (provider === "groq") {
        keyToSend = groqKey.trim() || undefined;
        modelToSend = groqSttModel;
      } else if (provider === "gemini") {
        keyToSend = geminiKey.trim() || undefined;
        modelToSend = llmModel;
      } else if (provider === "openai_compat") {
        keyToSend = openaiKey.trim() || groqKey.trim() || undefined;
        modelToSend = llmBackupModel;
        baseUrlToSend = llmBackupBaseUrl;
      }

      const res = await testSettingsConnection(provider, keyToSend, {
        model: modelToSend,
        base_url: baseUrlToSend,
      });
      setTestResults((prev) => ({ ...prev, [provider]: res }));
      showToast(res.ok ? "ok" : "err", res.detail);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error probando conexión";
      setTestResults((prev) => ({
        ...prev,
        [provider]: { ok: false, provider, latency_ms: 0, detail: msg },
      }));
      showToast("err", msg);
    } finally {
      setTestingProvider((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const renderKeyStatusBadge = (hasKey: boolean, masked: string, typedValue: string) => {
    if (typedValue.trim()) {
      return (
        <Badge tone="gold">
          <Sparkles className="h-3 w-3" /> Nueva clave por guardar
        </Badge>
      );
    }
    if (hasKey) {
      return (
        <Badge tone="success" className="font-mono">
          <CheckCircle2 className="h-3 w-3" /> Configurada ({masked})
        </Badge>
      );
    }
    return (
      <Badge tone="neutral">
        <AlertCircle className="h-3 w-3" /> Sin configurar
      </Badge>
    );
  };

  const renderTestResultBanner = (provider: ProviderId) => {
    const res = testResults[provider];
    if (!res) return null;
    return (
      <div
        className={`mt-3 flex items-center justify-between rounded-2xl border px-3.5 py-2 text-xs font-medium ${
          res.ok
            ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
            : "border-rose-400/30 bg-rose-400/10 text-rose-200"
        }`}
      >
        <span className="flex items-center gap-1.5">
          {res.ok ? (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-300" />
          ) : (
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-rose-300" />
          )}
          <span>{res.detail}</span>
        </span>
        {res.latency_ms > 0 && <span className="font-mono text-[11px] opacity-80">{res.latency_ms} ms</span>}
      </div>
    );
  };

  const spent = budget?.spent_usd ?? 0;
  const budgetRatio = Math.min(1, spent / Math.max(0.01, maxBudgetUsd || 1));

  return (
    <div className="space-y-6">
      {/* Toast Flotante */}
      {toast && (
        <div
          role="status"
          className={`ax-popover fixed bottom-6 right-6 z-50 flex max-w-md items-center gap-2.5 px-4 py-3 text-xs font-semibold transition-all ${
            toast.kind === "ok"
              ? "border-emerald-400/40 text-emerald-200"
              : "border-rose-400/40 text-rose-200"
          }`}
        >
          {toast.kind === "ok" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          )}
          <span>{toast.text}</span>
        </div>
      )}

      {/* Encabezado */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-amber-400/90">
            <Sliders className="h-3.5 w-3.5" /> Configuración del estudio
          </div>
          <h1 className="mt-1 text-xl font-bold tracking-tight text-slate-50 sm:text-2xl">
            Ajustes de tu Estudio
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            Elige qué servicios usar para crear tus clips, define tu límite de gasto y conecta Google Drive o FilmCraft NLE.
            {settings?.env_path && (
              <InfoTip label="Guardado inmediato">
                Tus cambios se aplican al instante sin necesidad de reiniciar la aplicación.
              </InfoTip>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button type="button" onClick={loadAll} disabled={loading} className={btnSecondary}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Recargar
          </button>

          <button type="submit" form="settings-form" disabled={saving || loading} className={btnPrimary}>
            {saving ? <SoftSpinner className="h-3.5 w-3.5" onAccent /> : <Save className="h-3.5 w-3.5" />}
            {saving ? "Guardando..." : "Guardar cambios"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs sm:text-sm font-medium text-rose-200">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {loading && !settings ? (
        <GlassCard className="flex h-64 items-center justify-center p-8 text-sm font-semibold text-slate-300">
          <SoftSpinner className="mr-3 h-5 w-5" />
          Cargando tus ajustes...
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[15.5rem_minmax(0,1fr)]">
          {/* Astryx settings-sidebar Navigation Rail */}
          <aside className="lg:sticky lg:top-20 lg:self-start">
            <GlassCard className="p-2.5 space-y-1">
              <div className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Categorías
              </div>
              {[
                {
                  id: "all" as const,
                  label: "Todas las secciones",
                  sub: "Vista completa",
                  icon: Sliders,
                },
                {
                  id: "stt" as const,
                  label: "1. Voz y Subtítulos",
                  sub: sttPrimary,
                  icon: Mic,
                },
                {
                  id: "llm" as const,
                  label: "2. Curación IA",
                  sub: llmPrimary,
                  icon: Cpu,
                },
                {
                  id: "budget" as const,
                  label: "3. Presupuesto y Avisos",
                  sub: `$${Number(maxBudgetUsd || 0).toFixed(2)} USD`,
                  icon: DollarSign,
                },
                {
                  id: "drive" as const,
                  label: "4. Google Drive",
                  sub:
                    driveStatus?.oauth_connected || settings?.drive_oauth_connected
                      ? "Conectado"
                      : driveMode,
                  icon: FolderSync,
                },
                {
                  id: "filmcraft" as const,
                  label: "5. FilmCraft & MCP",
                  sub: filmcraftStatus?.installed ? "Instalado" : "Verificar",
                  icon: Wifi,
                },
              ].map((cat) => {
                const Icon = cat.icon;
                const active = activeSection === cat.id;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setActiveSection(cat.id)}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors duration-150 cursor-pointer ${
                      active
                        ? "bg-amber-400/12 text-amber-300 font-semibold"
                        : "text-slate-300 hover:bg-white/[0.04] hover:text-white"
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <Icon
                        className={`h-3.5 w-3.5 shrink-0 ${
                          active ? "text-amber-300" : "text-slate-400"
                        }`}
                      />
                      <span className="truncate">{cat.label}</span>
                    </span>
                    <span className="shrink-0 rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                      {cat.sub}
                    </span>
                  </button>
                );
              })}
            </GlassCard>
          </aside>

          <form id="settings-form" onSubmit={handleSave} className="space-y-6">
          {/* 1. SECCIÓN VOZ A TEXTO (STT) */}
          <GlassCard
            as="section"
            className={`p-5 sm:p-6 ${
              activeSection !== "all" && activeSection !== "stt" ? "hidden" : ""
            }`}
          >
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-400/15 text-emerald-300">
                  <Mic className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    1. Servicio para escuchar tu voz (Subtítulos)
                  </h2>
                  <p className="text-xs text-slate-400">
                    Convierte lo que hablas en texto con el tiempo exacto de cada palabra para animar los subtítulos.
                  </p>
                </div>
              </div>
              <Badge tone="success">
                En uso: {sttPrimary} · Respaldo: {sttBackup}
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Servicio principal de voz
                </label>
                <select
                  value={sttPrimary}
                  onChange={(e) => setSttPrimary(e.target.value as "deepgram" | "groq" | "fixture")}
                  className={inputBase}
                >
                  <option value="deepgram">Deepgram Nova-3 — Más preciso con jerga de juegos (Recomendado)</option>
                  <option value="groq">Groq Whisper Turbo — Muy económico y rápido</option>
                  <option value="fixture">Modo de prueba sin internet ($0.00)</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Servicio de respaldo (entra solo si el principal falla)
                </label>
                <select
                  value={sttBackup}
                  onChange={(e) => setSttBackup(e.target.value as "groq" | "deepgram" | "fixture" | "none")}
                  className={inputBase}
                >
                  <option value="groq">Groq Whisper Turbo</option>
                  <option value="deepgram">Deepgram Nova-3</option>
                  <option value="fixture">Modo de prueba local</option>
                  <option value="none">Sin respaldo</option>
                </select>
              </div>
            </div>

            {/* Credenciales STT */}
            <div className="mt-6 grid gap-5 md:grid-cols-2">
              {/* Deepgram */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-emerald-300" />
                    <span className="text-xs font-extrabold text-slate-100">Clave de Deepgram</span>
                  </div>
                  {renderKeyStatusBadge(
                    Boolean(settings?.has_deepgram_key),
                    settings?.deepgram_api_key || "",
                    deepgramKey
                  )}
                </div>

                <div className="relative flex items-center">
                  <input
                    type={showKey.deepgram ? "text" : "password"}
                    value={deepgramKey}
                    onChange={(e) => setDeepgramKey(e.target.value)}
                    placeholder={
                      settings?.has_deepgram_key
                        ? `Clave guardada (${settings.deepgram_api_key}) — escribe si quieres cambiarla`
                        : "Pega aquí tu clave de Deepgram"
                    }
                    autoComplete="off"
                    className={`${inputBase} pr-10 font-mono text-xs`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((p) => ({ ...p, deepgram: !p.deepgram }))}
                    title={showKey.deepgram ? "Ocultar clave" : "Mostrar clave"}
                    className="absolute right-3 text-slate-400 transition hover:text-slate-100 cursor-pointer"
                  >
                    {showKey.deepgram ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span>Versión:</span>
                    <input
                      type="text"
                      value={deepgramModel}
                      onChange={(e) => setDeepgramModel(e.target.value)}
                      className="w-28 rounded-xl border border-white/10 bg-slate-950/70 px-2.5 py-1 font-mono text-xs text-slate-200 focus:border-amber-300/60 focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => handleTestConnection("deepgram")}
                    disabled={testingProvider.deepgram}
                    className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}
                  >
                    {testingProvider.deepgram ? (
                      <SoftSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <Wifi className="h-3.5 w-3.5" />
                    )}
                    Probar conexión
                  </button>
                </div>
                {renderTestResultBanner("deepgram")}
              </div>

              {/* Groq */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-amber-300" />
                    <span className="text-xs font-extrabold text-slate-100">Clave de Groq Cloud</span>
                  </div>
                  {renderKeyStatusBadge(Boolean(settings?.has_groq_key), settings?.groq_api_key || "", groqKey)}
                </div>

                <div className="relative flex items-center">
                  <input
                    type={showKey.groq ? "text" : "password"}
                    value={groqKey}
                    onChange={(e) => setGroqKey(e.target.value)}
                    placeholder={
                      settings?.has_groq_key
                        ? `Clave guardada (${settings.groq_api_key}) — escribe si quieres cambiarla`
                        : "Pega aquí tu clave de Groq (gsk_...)"
                    }
                    autoComplete="off"
                    className={`${inputBase} pr-10 font-mono text-xs`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((p) => ({ ...p, groq: !p.groq }))}
                    title={showKey.groq ? "Ocultar clave" : "Mostrar clave"}
                    className="absolute right-3 text-slate-400 transition hover:text-slate-100 cursor-pointer"
                  >
                    {showKey.groq ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span>Versión:</span>
                    <input
                      type="text"
                      value={groqSttModel}
                      onChange={(e) => setGroqSttModel(e.target.value)}
                      className="w-40 rounded-xl border border-white/10 bg-slate-950/70 px-2.5 py-1 font-mono text-xs text-slate-200 focus:border-amber-300/60 focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => handleTestConnection("groq")}
                    disabled={testingProvider.groq}
                    className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}
                  >
                    {testingProvider.groq ? <SoftSpinner className="h-3.5 w-3.5" /> : <Wifi className="h-3.5 w-3.5" />}
                    Probar conexión
                  </button>
                </div>
                {renderTestResultBanner("groq")}
              </div>
            </div>
          </GlassCard>

          {/* 2. SECCIÓN CURACIÓN NARRATIVA (LLM) */}
          <GlassCard
            as="section"
            className={`p-5 sm:p-6 ${
              activeSection !== "all" && activeSection !== "llm" ? "hidden" : ""
            }`}
          >
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400/15 text-amber-300">
                  <Cpu className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    2. Inteligencia Artificial para elegir los mejores momentos
                  </h2>
                  <p className="text-xs text-slate-400">
                    Analiza lo que pasó en la partida para elegir las jugadas más entretenidas y redactar sus títulos.
                  </p>
                </div>
              </div>
              <Badge tone="gold">
                En uso: {llmPrimary} ({llmModel})
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Servicio principal de IA
                </label>
                <select
                  value={llmPrimary}
                  onChange={(e) => setLlmPrimary(e.target.value as "gemini" | "openai_compat" | "fixture")}
                  className={inputBase}
                >
                  <option value="gemini">Google Gemini — Rápido y con capa gratuita (Recomendado)</option>
                  <option value="openai_compat">
                    OpenAI / Groq / Compatible
                  </option>
                  <option value="fixture">Modo de prueba sin internet ($0.00)</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Modelo de IA principal
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                    placeholder="ej. gemini-3.5-flash-lite"
                    className={`${inputBase} font-mono text-xs`}
                  />
                  <select
                    aria-label="Presets de modelo principal"
                    value=""
                    onChange={(e) => {
                      if (e.target.value) setLlmModel(e.target.value);
                    }}
                    className="w-44 shrink-0 rounded-2xl border border-white/10 bg-slate-900/80 px-3 py-2 text-xs font-semibold text-slate-300 focus:border-amber-300/60 focus:outline-none"
                  >
                    <option value="">Elegir sugerido...</option>
                    {GEMINI_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.value}
                      </option>
                    ))}
                    {OPENAI_COMPAT_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.value}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Servicio de respaldo
                </label>
                <select
                  value={llmBackup}
                  onChange={(e) => setLlmBackup(e.target.value as "openai_compat" | "gemini" | "fixture" | "none")}
                  className={inputBase}
                >
                  <option value="openai_compat">OpenAI / Compatible</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="fixture">Modo de prueba local</option>
                  <option value="none">Sin respaldo</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Modelo y dirección del servicio de respaldo
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={llmBackupModel}
                    onChange={(e) => setLlmBackupModel(e.target.value)}
                    placeholder="gpt-6-luna"
                    className={`${inputBase} font-mono text-xs`}
                  />
                  <input
                    type="text"
                    value={llmBackupBaseUrl}
                    onChange={(e) => setLlmBackupBaseUrl(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                    className={`${inputBase} font-mono text-xs`}
                  />
                </div>
              </div>
            </div>

            {/* Credenciales LLM */}
            <div className="mt-6 grid gap-5 md:grid-cols-2">
              {/* Gemini */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-amber-300" />
                    <span className="text-xs font-extrabold text-slate-100">Clave de Google Gemini</span>
                  </div>
                  {renderKeyStatusBadge(Boolean(settings?.has_gemini_key), settings?.gemini_api_key || "", geminiKey)}
                </div>

                <div className="relative flex items-center">
                  <input
                    type={showKey.gemini ? "text" : "password"}
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    placeholder={
                      settings?.has_gemini_key
                        ? `Clave guardada (${settings.gemini_api_key}) — escribe si quieres cambiarla`
                        : "Pega aquí tu clave de Google AI Studio (AIza...)"
                    }
                    autoComplete="off"
                    className={`${inputBase} pr-10 font-mono text-xs`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((p) => ({ ...p, gemini: !p.gemini }))}
                    title={showKey.gemini ? "Ocultar clave" : "Mostrar clave"}
                    className="absolute right-3 text-slate-400 transition hover:text-slate-100 cursor-pointer"
                  >
                    {showKey.gemini ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                <div className="mt-3.5 flex items-center justify-between gap-2">
                  <span className="text-xs text-slate-400">Conexión con Google AI Studio</span>
                  <button
                    type="button"
                    onClick={() => handleTestConnection("gemini")}
                    disabled={testingProvider.gemini}
                    className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}
                  >
                    {testingProvider.gemini ? (
                      <SoftSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <Wifi className="h-3.5 w-3.5" />
                    )}
                    Probar conexión
                  </button>
                </div>
                {renderTestResultBanner("gemini")}
              </div>

              {/* OpenAI / Compatible */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-sky-300" />
                    <span className="text-xs font-extrabold text-slate-100">Clave de OpenAI / Compatible</span>
                  </div>
                  {renderKeyStatusBadge(Boolean(settings?.has_openai_key), settings?.openai_api_key || "", openaiKey)}
                </div>

                <div className="relative flex items-center">
                  <input
                    type={showKey.openai ? "text" : "password"}
                    value={openaiKey}
                    onChange={(e) => setOpenaiKey(e.target.value)}
                    placeholder={
                      settings?.has_openai_key
                        ? `Clave guardada (${settings.openai_api_key}) — escribe si quieres cambiarla`
                        : "Pega aquí tu clave de OpenAI u OpenRouter (sk-...)"
                    }
                    autoComplete="off"
                    className={`${inputBase} pr-10 font-mono text-xs`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((p) => ({ ...p, openai: !p.openai }))}
                    title={showKey.openai ? "Ocultar clave" : "Mostrar clave"}
                    className="absolute right-3 text-slate-400 transition hover:text-slate-100 cursor-pointer"
                  >
                    {showKey.openai ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                <div className="mt-3.5 flex items-center justify-between gap-2">
                  <span className="truncate text-xs text-slate-400" title={llmBackupBaseUrl}>
                    Servidor: {llmBackupBaseUrl}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleTestConnection("openai_compat")}
                    disabled={testingProvider.openai_compat}
                    className={`${btnSecondary} shrink-0 !px-3.5 !py-1.5 !text-xs`}
                  >
                    {testingProvider.openai_compat ? (
                      <SoftSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <Wifi className="h-3.5 w-3.5" />
                    )}
                    Probar conexión
                  </button>
                </div>
                {renderTestResultBanner("openai_compat")}
              </div>
            </div>
          </GlassCard>

          {/* 3. SECCIÓN PRESUPUESTO Y LÍMITES */}
          <GlassCard
            as="section"
            className={`p-5 sm:p-6 ${
              activeSection !== "all" && activeSection !== "budget" ? "hidden" : ""
            }`}
          >
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400/15 text-amber-300">
                  <DollarSign className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    3. Límite de gasto, espacio en disco y avisos
                  </h2>
                  <p className="text-xs text-slate-400">
                    Te protege de gastos inesperados deteniendo nuevas consultas si llegas al límite que elijas.
                  </p>
                </div>
              </div>
              <Badge tone="gold">
                <ShieldCheck className="h-3.5 w-3.5" /> Usado: ${spent.toFixed(2)} de $
                {Number(maxBudgetUsd || 0).toFixed(2)} USD
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Clips por sesión (por defecto)
                </label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="20"
                  value={autoRenderTopK}
                  onChange={(e) => setAutoRenderTopK(parseInt(e.target.value, 10) || 5)}
                  className={`${inputBase} font-mono font-bold text-amber-300`}
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Cantidad predeterminada (1–20) si no indicas otra al crear la sesión.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Límite máximo de gasto (USD)
                </label>
                <input
                  type="number"
                  step="0.25"
                  min="0.10"
                  max="10000"
                  value={maxBudgetUsd}
                  onChange={(e) => setMaxBudgetUsd(parseFloat(e.target.value) || 0)}
                  className={`${inputBase} font-mono font-bold text-amber-300`}
                />
                <ProgressBar value={budgetRatio} className="mt-2.5" />
                <p className="mt-1.5 text-xs text-slate-400">
                  Te quedan{" "}
                  <strong className="font-mono text-slate-200">
                    ${Math.max(0, (Number(maxBudgetUsd) || 0) - spent).toFixed(2)} USD
                  </strong>{" "}
                  disponibles.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Días antes de limpiar archivos temporales
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  max="365"
                  value={tempTtlDays}
                  onChange={(e) => setTempTtlDays(parseFloat(e.target.value) || 0)}
                  className={`${inputBase} font-mono`}
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Libera espacio en tu disco automáticamente sin borrar tus videos ni tus análisis guardados.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Enlace de avisos (Discord o Slack)
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://discord.com/api/webhooks/..."
                  className={`${inputBase} font-mono text-xs`}
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Opcional: te avisa con un mensaje cuando los clips de tu sesión terminan de crearse.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* 4. SECCIÓN CONEXIÓN DIRECTA A GOOGLE DRIVE (OAUTH 2.0 / SERVICIO / LOCAL) */}
          <GlassCard
            as="section"
            className={`p-5 sm:p-6 ${
              activeSection !== "all" && activeSection !== "drive" ? "hidden" : ""
            }`}
          >
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-400/15 text-sky-300">
                  <FolderSync className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    4. Conexión con Google Drive
                  </h2>
                  <p className="text-xs text-slate-400">
                    Conecta tu cuenta de Google para explorar tus carpetas y elegir tus videos en un clic, o usa una
                    carpeta sincronizada en tu PC.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {loadingDrive && !driveStatus && !settings?.drive_oauth_connected ? (
                  <Badge tone="neutral">
                    <SoftSpinner className="h-3 w-3" /> Verificando Drive...
                  </Badge>
                ) : driveStatus?.oauth_connected || settings?.drive_oauth_connected ? (
                  <Badge tone="success">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Cuenta vinculada
                    {driveStatus?.user_email ? ` (${driveStatus.user_email})` : ""}
                  </Badge>
                ) : (
                  <Badge tone="neutral">Modo actual: {driveMode}</Badge>
                )}
              </div>
            </div>

            <div className="grid gap-5 md:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  ¿Cómo quieres usar Google Drive?
                </label>
                <select
                  value={driveMode}
                  onChange={(e) =>
                    setDriveMode(e.target.value as "local" | "oauth" | "service_account" | "disabled")
                  }
                  className={inputBase}
                >
                  <option value="oauth">Cuenta personal de Google (Explorador directo)</option>
                  <option value="local">Carpeta de Google Drive instalada en tu PC</option>
                  <option value="service_account">Cuenta de servicio empresarial</option>
                  <option value="disabled">No usar Google Drive</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Carpeta inicial en tu Drive
                </label>
                <input
                  type="text"
                  value={driveRootFolderId}
                  onChange={(e) => setDriveRootFolderId(e.target.value)}
                  placeholder="root (Mi unidad) o ID de carpeta"
                  className={`${inputBase} font-mono text-xs`}
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  Déjalo vacío para ver todas tus carpetas desde «Mi unidad».
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Revisar grabaciones nuevas cada (segundos)
                </label>
                <input
                  type="number"
                  step="10"
                  min="5"
                  max="86400"
                  value={drivePollSec}
                  onChange={(e) => setDrivePollSec(parseFloat(e.target.value) || 120)}
                  className={`${inputBase} font-mono`}
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  Cada cuánto tiempo buscamos videos nuevos en tu carpeta de Entradas.
                </p>
              </div>
            </div>

            {/* Credenciales OAuth 2.0 */}
            <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-sky-300" />
                    <span className="text-xs font-extrabold text-slate-100">ID de Cliente de Google (Client ID)</span>
                  </div>
                  <Badge tone={driveClientId.trim() ? "info" : "neutral"}>
                    {driveClientId.trim() ? "Listo" : "Opcional"}
                  </Badge>
                </div>
                <input
                  type="text"
                  value={driveClientId}
                  onChange={(e) => setDriveClientId(e.target.value)}
                  placeholder="1234567890-abc.apps.googleusercontent.com"
                  autoComplete="off"
                  className={`${inputBase} font-mono text-xs`}
                />
                <p className="mt-2 text-[11px] text-slate-400">
                  Dirección de retorno en Google Cloud:{" "}
                  <code className="text-slate-200">http://127.0.0.1:8790/drive/auth/callback</code>
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-amber-300" />
                    <span className="text-xs font-extrabold text-slate-100">Clave Secreta de Google (Client Secret)</span>
                  </div>
                  {renderKeyStatusBadge(
                    Boolean(settings?.has_drive_client_secret),
                    settings?.drive_client_secret || "",
                    driveClientSecret
                  )}
                </div>
                <div className="relative flex items-center">
                  <input
                    type={showKey.driveSecret ? "text" : "password"}
                    value={driveClientSecret}
                    onChange={(e) => setDriveClientSecret(e.target.value)}
                    placeholder={
                      settings?.has_drive_client_secret
                        ? `Secreto guardado (${settings.drive_client_secret}) — escribe si quieres cambiarlo`
                        : "Pega tu Client Secret de Google (GOCSPX-...)"
                    }
                    autoComplete="off"
                    className={`${inputBase} pr-10 font-mono text-xs`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((p) => ({ ...p, driveSecret: !p.driveSecret }))}
                    title={showKey.driveSecret ? "Ocultar secreto" : "Mostrar secreto"}
                    className="absolute right-3 text-slate-400 transition hover:text-slate-100 cursor-pointer"
                  >
                    {showKey.driveSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-slate-400">
                  Se guarda de forma segura en tu propio equipo para que no tengas que iniciar sesión cada día.
                </p>
              </div>
            </div>

            {/* Acciones de vinculación OAuth 2.0 */}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleStartDriveOAuth}
                  disabled={connectingDrive}
                  className={btnPrimary}
                >
                  {connectingDrive ? <SoftSpinner className="h-4 w-4" onAccent /> : <Link2 className="h-4 w-4" />}
                  {driveStatus?.oauth_connected || settings?.drive_oauth_connected
                    ? "Cambiar cuenta de Google Drive"
                    : "Vincular mi cuenta de Google Drive"}
                </button>

                {(driveStatus?.oauth_connected || settings?.drive_oauth_connected) && (
                  <button
                    type="button"
                    onClick={handleDisconnectDrive}
                    disabled={connectingDrive}
                    className={btnSecondary}
                  >
                    <Unlink className="h-4 w-4 text-rose-300" />
                    Desvincular cuenta
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={driveAuthCode}
                  onChange={(e) => setDriveAuthCode(e.target.value)}
                  placeholder="Código manual (si la ventana no cerró sola)"
                  className="w-64 rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 font-mono text-xs text-slate-200 placeholder:text-slate-500 focus:border-amber-300/60 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleExchangeDriveCode}
                  disabled={connectingDrive || !driveAuthCode.trim()}
                  className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}
                >
                  Confirmar código
                </button>
              </div>
            </div>
          </GlassCard>

          {/* 5. SECCIÓN INTEGRACIÓN FILMCRAFT NLE */}
          <GlassCard
            as="section"
            className={`p-5 sm:p-6 ${
              activeSection !== "all" && activeSection !== "filmcraft" ? "hidden" : ""
            }`}
          >
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-400 border border-sky-500/30">
                  <Sliders className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-base font-extrabold text-white">FilmCraft NLE & Copiloto MCP</h2>
                  <p className="text-xs text-slate-400">
                    Edición profesional no lineal y asistencia conversacional local con Claude Desktop.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
                    filmcraftStatus?.installed
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      filmcraftStatus?.installed ? "bg-emerald-400" : "bg-amber-400"
                    }`}
                  />
                  {filmcraftStatus?.installed
                    ? `Instalado (v${filmcraftStatus.version || "0.20.1"})`
                    : "No detectado"}
                </span>
                <button
                  type="button"
                  onClick={handleCheckFilmcraft}
                  disabled={checkingFilmcraft}
                  className={`${btnSecondary} !px-3 !py-1 !text-xs`}
                >
                  {checkingFilmcraft ? (
                    <SoftSpinner className="h-3.5 w-3.5" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                  Comprobar
                </button>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 text-xs">
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
                <span className="font-bold text-slate-200">Ruta de la aplicación</span>
                <p className="mt-1 font-mono text-[11px] text-slate-400 break-all">
                  {filmcraftStatus?.path || "C:\\...\\AppData\\Local\\Programs\\ArtCraft\\FilmCraft\\filmcraft.exe"}
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
                <span className="font-bold text-slate-200">Bridge de control loopback</span>
                <p className="mt-1 text-slate-400">
                  Puerto: <span className="font-mono text-slate-200">9876</span> · Estado:{" "}
                  <span
                    className={`font-bold ${
                      filmcraftStatus?.bridge_up ? "text-emerald-400" : "text-slate-400"
                    }`}
                  >
                    {filmcraftStatus?.bridge_up ? "Activo (127.0.0.1:9876)" : "Inactivo (se abrirá al pulsar)"}
                  </span>
                </p>
              </div>
            </div>
          </GlassCard>

          {/* Barra inferior de acciones */}
          <GlassCard className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
            <div className="text-xs text-slate-400">
              Las claves que dejes en blanco conservarán la que ya tenías guardada.
            </div>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => handleTestConnection("fixture")}
                className={btnSecondary}
              >
                <Wifi className="h-3.5 w-3.5" />
                Probar modo sin internet
              </button>
              <button type="submit" disabled={saving} className={btnPrimary}>
                {saving ? <SoftSpinner className="h-3.5 w-3.5" onAccent /> : <Save className="h-3.5 w-3.5" />}
                {saving ? "Guardando..." : "Guardar cambios"}
              </button>
            </div>
          </GlassCard>
        </form>
        </div>
      )}
    </div>
  );
}
