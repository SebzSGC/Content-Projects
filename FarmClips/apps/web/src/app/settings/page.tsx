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
  Sparkles,
  Unlink,
  Wifi,
} from "lucide-react";
import {
  type AppSettings,
  type BudgetSummary,
  type DriveStatus,
  type TestConnectionResult,
  completeDriveAuthCallback,
  disconnectDriveAuth,
  fetchBudget,
  fetchDriveAuthUrl,
  fetchDriveStatus,
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
  const [loading, setLoading] = useState(true);
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
      const [s, b, d] = await Promise.all([
        getSettings(),
        fetchBudget(),
        fetchDriveStatus().catch(() => null),
      ]);
      applyLoadedSettings(s);
      setBudget(b);
      setDriveStatus(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la configuración del servidor.");
    } finally {
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
      const [freshBudget, freshDrive] = await Promise.all([
        fetchBudget(),
        fetchDriveStatus().catch(() => null),
      ]);
      setBudget(freshBudget);
      setDriveStatus(freshDrive);
      showToast("ok", "Configuración guardada en .env y aplicada en memoria.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al guardar la configuración";
      setError(msg);
      showToast("err", msg);
    } finally {
      setSaving(false);
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
    <main className="mx-auto max-w-[1180px] px-4 py-8 sm:px-6">
      {/* Toast Flotante */}
      {toast && (
        <div
          role="status"
          className={`fixed bottom-6 right-6 z-50 flex max-w-md items-center gap-2.5 rounded-2xl border px-4 py-3 text-xs font-bold shadow-2xl backdrop-blur-xl transition-all ${
            toast.kind === "ok"
              ? "border-emerald-400/40 bg-slate-900/95 text-emerald-200"
              : "border-rose-400/40 bg-slate-900/95 text-rose-200"
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
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400">
            <Link href="/sessions" className="inline-flex items-center gap-1 transition hover:text-slate-100">
              <ArrowLeft className="h-3.5 w-3.5" /> Volver a Sesiones
            </Link>
            <span>/</span>
            <span className="text-amber-300">Configuración</span>
          </div>
          <h1 className="mt-1.5 text-2xl font-black tracking-tight text-slate-50 sm:text-3xl">
            Configuración y Proveedores de IA
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Gestiona tus API Keys, modelos principales/respaldo y límites de presupuesto con aplicación inmediata en
            memoria.
            {settings?.env_path && (
              <InfoTip label="Archivo de persistencia">
                Los cambios se guardan de forma segura en{" "}
                <span className="font-mono text-slate-100">{settings.env_path}</span> sin necesidad de reiniciar el
                servidor.
              </InfoTip>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button type="button" onClick={loadAll} disabled={loading} className={btnSecondary}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Recargar
          </button>

          <button type="submit" form="settings-form" disabled={saving || loading} className={btnPrimary}>
            {saving ? <SoftSpinner className="h-4 w-4" onAccent /> : <Save className="h-4 w-4" />}
            {saving ? "Guardando..." : "Guardar Configuración"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-2.5 rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm font-medium text-rose-200">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {loading && !settings ? (
        <GlassCard className="flex h-64 items-center justify-center p-8 text-sm font-semibold text-slate-300">
          <SoftSpinner className="mr-3 h-5 w-5" />
          Cargando configuración actual...
        </GlassCard>
      ) : (
        <form id="settings-form" onSubmit={handleSave} className="space-y-6">
          {/* 1. SECCIÓN VOZ A TEXTO (STT) */}
          <GlassCard as="section" className="p-6 sm:p-7">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-400/15 text-emerald-300">
                  <Mic className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    1. Voz a Texto (STT — Transcripción por Palabra)
                  </h2>
                  <p className="text-xs text-slate-400">
                    Transcribe únicamente el audio Opus ligero del micrófono con marcas de tiempo por palabra y
                    vocabulario gaming.
                  </p>
                </div>
              </div>
              <Badge tone="success">
                Activo: {sttPrimary} → Respaldo: {sttBackup}
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Proveedor Principal STT (<code className="text-amber-300">CLIPS_STT_PRIMARY</code>)
                </label>
                <select
                  value={sttPrimary}
                  onChange={(e) => setSttPrimary(e.target.value as "deepgram" | "groq" | "fixture")}
                  className={inputBase}
                >
                  <option value="deepgram">deepgram — Deepgram Nova-3 (Keyterms + Timestamps exactos)</option>
                  <option value="groq">groq — Groq Whisper Large v3 Turbo (Económico y veloz)</option>
                  <option value="fixture">fixture — Modo Pruebas Offline ($0.00 sin red)</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Proveedor de Respaldo Automático (<code className="text-slate-400">CLIPS_STT_BACKUP</code>)
                </label>
                <select
                  value={sttBackup}
                  onChange={(e) => setSttBackup(e.target.value as "groq" | "deepgram" | "fixture" | "none")}
                  className={inputBase}
                >
                  <option value="groq">groq — Groq Whisper Large v3 Turbo</option>
                  <option value="deepgram">deepgram — Deepgram Nova-3</option>
                  <option value="fixture">fixture — Fixtures grabadas locales</option>
                  <option value="none">none — Sin respaldo</option>
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
                    <span className="text-xs font-extrabold text-slate-100">DEEPGRAM_API_KEY</span>
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
                        ? `Clave guardada (${settings.deepgram_api_key}) — escribe para reemplazar`
                        : "Pega tu clave de Deepgram (ej. dg_...)"
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
                    <span>Modelo:</span>
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
                    Probar Conexión
                  </button>
                </div>
                {renderTestResultBanner("deepgram")}
              </div>

              {/* Groq */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-amber-300" />
                    <span className="text-xs font-extrabold text-slate-100">GROQ_API_KEY</span>
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
                        ? `Clave guardada (${settings.groq_api_key}) — escribe para reemplazar`
                        : "Pega tu clave de Groq Cloud (ej. gsk_...)"
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
                    <span>Modelo:</span>
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
                    Probar Conexión
                  </button>
                </div>
                {renderTestResultBanner("groq")}
              </div>
            </div>
          </GlassCard>

          {/* 2. SECCIÓN CURACIÓN NARRATIVA (LLM) */}
          <GlassCard as="section" className="p-6 sm:p-7">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400/15 text-amber-300">
                  <Cpu className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    2. Curación Narrativa (LLM — Selección por IDs de Frase)
                  </h2>
                  <p className="text-xs text-slate-400">
                    Evalúa la línea de tiempo compacta (`u0001..u9999` + picos acústicos/HUD) y sugiere los mejores
                    momentos.
                  </p>
                </div>
              </div>
              <Badge tone="gold">
                Activo: {llmPrimary} ({llmModel})
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Proveedor Principal LLM (<code className="text-amber-300">CLIPS_LLM_PRIMARY</code>)
                </label>
                <select
                  value={llmPrimary}
                  onChange={(e) => setLlmPrimary(e.target.value as "gemini" | "openai_compat" | "fixture")}
                  className={inputBase}
                >
                  <option value="gemini">gemini — Google Gemini API (Structured Outputs nativo)</option>
                  <option value="openai_compat">
                    openai_compat — OpenAI / Groq / OpenRouter / Ollama Compatible
                  </option>
                  <option value="fixture">fixture — Modo Pruebas Offline ($0.00 sin red)</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Modelo Principal LLM (<code className="text-amber-300">CLIPS_LLM_MODEL</code>)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                    placeholder="ej. gemini-3.5-flash-lite o gpt-6-luna"
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
                    <option value="">Presets...</option>
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
                  Proveedor de Respaldo LLM (<code className="text-slate-400">CLIPS_LLM_BACKUP</code>)
                </label>
                <select
                  value={llmBackup}
                  onChange={(e) => setLlmBackup(e.target.value as "openai_compat" | "gemini" | "fixture" | "none")}
                  className={inputBase}
                >
                  <option value="openai_compat">openai_compat — OpenAI / Compatible</option>
                  <option value="gemini">gemini — Google Gemini</option>
                  <option value="fixture">fixture — Fixtures locales</option>
                  <option value="none">none — Sin respaldo</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Modelo y Base URL OpenAI-Compatible (<code className="text-slate-400">CLIPS_LLM_BACKUP_MODEL</code>)
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
                    <span className="text-xs font-extrabold text-slate-100">GEMINI_API_KEY</span>
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
                        ? `Clave guardada (${settings.gemini_api_key}) — escribe para reemplazar`
                        : "Pega tu clave de Google AI Studio (ej. AIza...)"
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
                  <span className="text-xs text-slate-400">Google Generative Language API (`v1beta`)</span>
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
                    Probar Conexión
                  </button>
                </div>
                {renderTestResultBanner("gemini")}
              </div>

              {/* OpenAI / Compatible */}
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-sky-300" />
                    <span className="text-xs font-extrabold text-slate-100">OPENAI_API_KEY</span>
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
                        ? `Clave guardada (${settings.openai_api_key}) — escribe para reemplazar`
                        : "Pega tu clave de OpenAI / OpenRouter (ej. sk-...)"
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
                    Endpoint: {llmBackupBaseUrl}
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
                    Probar Conexión
                  </button>
                </div>
                {renderTestResultBanner("openai_compat")}
              </div>
            </div>
          </GlassCard>

          {/* 3. SECCIÓN PRESUPUESTO Y LÍMITES */}
          <GlassCard as="section" className="p-6 sm:p-7">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400/15 text-amber-300">
                  <DollarSign className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    3. Presupuesto, Límites y Operación
                  </h2>
                  <p className="text-xs text-slate-400">
                    El orquestador detiene nuevas peticiones externas si el gasto acumulado alcanza el tope configurado
                    (las llamadas en caché SQLite siguen costando $0.00).
                  </p>
                </div>
              </div>
              <Badge tone="gold">
                <ShieldCheck className="h-3.5 w-3.5" /> Consumido: ${spent.toFixed(4)} / $
                {Number(maxBudgetUsd || 0).toFixed(2)} USD
              </Badge>
            </div>

            <div className="grid gap-5 md:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Tope Máximo de Presupuesto USD (<code className="text-amber-300">CLIPS_MAX_BUDGET_USD</code>)
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
                  Saldo restante:{" "}
                  <strong className="font-mono text-slate-200">
                    ${Math.max(0, (Number(maxBudgetUsd) || 0) - spent).toFixed(4)} USD
                  </strong>{" "}
                  ({budget?.calls_count ?? 0} llamadas cacheadas)
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Retención de Temporales WAV/Opus (<code className="text-slate-400">CLIPS_TEMP_TTL_DAYS</code>)
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
                  Días antes de purgar archivos intermedios en sesiones entregadas (conserva Parquet y caché $0.00).
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Webhook de Entrega (<code className="text-slate-400">CLIPS_WEBHOOK_URL</code>)
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://discord.com/api/webhooks/..."
                  className={`${inputBase} font-mono text-xs`}
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Opcional (Discord, Slack o HTTP JSON) al finalizar la subida a <code>Salidas/</code>.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* 4. SECCIÓN CONEXIÓN DIRECTA A GOOGLE DRIVE (OAUTH 2.0 / SERVICIO / LOCAL) */}
          <GlassCard as="section" className="p-6 sm:p-7">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3.5">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-400/15 text-sky-300">
                  <FolderSync className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-extrabold text-slate-50">
                    4. Conexión Directa a Google Drive (OAuth 2.0 y Explorador)
                  </h2>
                  <p className="text-xs text-slate-400">
                    Vincula tu cuenta personal o Workspace por OAuth 2.0 (`data/drive_oauth_token.json`) para explorar
                    carpetas y elegir `gameplay` + `camara` en 1 clic, o usa Cuenta de Servicio / espejo local.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {driveStatus?.oauth_connected || settings?.drive_oauth_connected ? (
                  <Badge tone="success">
                    <CheckCircle2 className="h-3.5 w-3.5" /> OAuth Conectado
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
                  Modo de Conexión Drive (<code className="text-amber-300">CLIPS_DRIVE_MODE</code>)
                </label>
                <select
                  value={driveMode}
                  onChange={(e) =>
                    setDriveMode(e.target.value as "local" | "oauth" | "service_account" | "disabled")
                  }
                  className={inputBase}
                >
                  <option value="oauth">oauth — Conexión directa OAuth 2.0 (Cuenta de Google)</option>
                  <option value="local">local — Espejo local / Google Drive for Desktop</option>
                  <option value="service_account">service_account — Cuenta de Servicio JSON</option>
                  <option value="disabled">disabled — Deshabilitado</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Carpeta Raíz en Drive (<code className="text-slate-400">CLIPS_DRIVE_ROOT_FOLDER_ID</code>)
                </label>
                <input
                  type="text"
                  value={driveRootFolderId}
                  onChange={(e) => setDriveRootFolderId(e.target.value)}
                  placeholder="root (Mi unidad) o ID de carpeta"
                  className={`${inputBase} font-mono text-xs`}
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  Deja vacío o <code>root</code> en OAuth para explorar desde &quot;Mi unidad&quot;.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">
                  Intervalo de Vigilancia (<code className="text-slate-400">CLIPS_DRIVE_POLL_SEC</code>)
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
                  Segundos entre revisiones automáticas de <code>Entradas/</code>.
                </p>
              </div>
            </div>

            {/* Credenciales OAuth 2.0 */}
            <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-sky-300" />
                    <span className="text-xs font-extrabold text-slate-100">CLIPS_DRIVE_CLIENT_ID</span>
                  </div>
                  <Badge tone={driveClientId.trim() ? "info" : "neutral"}>
                    {driveClientId.trim() ? "Configurado" : "Requerido para OAuth"}
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
                  Redirect URI autorizado en Google Cloud Console:{" "}
                  <code className="text-slate-200">http://127.0.0.1:8790/drive/auth/callback</code>
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-amber-300" />
                    <span className="text-xs font-extrabold text-slate-100">CLIPS_DRIVE_CLIENT_SECRET</span>
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
                        ? `Secreto guardado (${settings.drive_client_secret}) — escribe para reemplazar`
                        : "Pega tu Client Secret de Google OAuth (ej. GOCSPX-...)"
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
                  El <code>refresh_token</code> se guarda localmente en <code>data/drive_oauth_token.json</code>.
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
                    ? "Reconectar Google Drive (OAuth 2.0)"
                    : "Conectar con Google Drive (OAuth 2.0)"}
                </button>

                {(driveStatus?.oauth_connected || settings?.drive_oauth_connected) && (
                  <button
                    type="button"
                    onClick={handleDisconnectDrive}
                    disabled={connectingDrive}
                    className={btnSecondary}
                  >
                    <Unlink className="h-4 w-4 text-rose-300" />
                    Desconectar cuenta
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={driveAuthCode}
                  onChange={(e) => setDriveAuthCode(e.target.value)}
                  placeholder="O pega código OAuth manual..."
                  className="w-52 rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 font-mono text-xs text-slate-200 placeholder:text-slate-500 focus:border-amber-300/60 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleExchangeDriveCode}
                  disabled={connectingDrive || !driveAuthCode.trim()}
                  className={`${btnSecondary} !px-3.5 !py-1.5 !text-xs`}
                >
                  Canjear código
                </button>
              </div>
            </div>
          </GlassCard>

          {/* Barra inferior de acciones */}
          <GlassCard className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
            <div className="text-xs text-slate-400">
              Las claves dejadas en blanco o enmascaradas conservan intacto su valor actual en{" "}
              <code className="font-mono text-slate-200">.env</code>.
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => handleTestConnection("fixture")}
                className={btnSecondary}
              >
                <Wifi className="h-4 w-4" />
                Probar Modo Offline
              </button>
              <button type="submit" disabled={saving} className={btnPrimary}>
                {saving ? <SoftSpinner className="h-4 w-4" onAccent /> : <Save className="h-4 w-4" />}
                {saving ? "Guardando..." : "Guardar Configuración"}
              </button>
            </div>
          </GlassCard>
        </form>
      )}
    </main>
  );
}
