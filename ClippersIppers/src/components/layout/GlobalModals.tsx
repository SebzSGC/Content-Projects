"use client";

import React, { useState } from "react";
import { useAtom } from "jotai";
import { useRouter } from "next/navigation";
import {
  activeModalAtom,
  aiConfigAtom,
  clipsAtom,
  projectsAtom,
} from "@/store/opusStore";
import {
  X,
  Search,
  Sparkles,
  Check,
  AlertCircle,
  ExternalLink,
  Eye,
  EyeOff,
  Film,
  ArrowRight,
} from "lucide-react";

export function GlobalModals() {
  const [activeModal, setActiveModal] = useAtom(activeModalAtom);
  const [projects] = useAtom(projectsAtom);
  const [clips] = useAtom(clipsAtom);
  const router = useRouter();

  // Search Modal State
  const [searchQuery, setSearchQuery] = useState("");

  // AI Connection Modal State
  const [aiConfig, setAiConfig] = useAtom(aiConfigAtom);
  const [selectedAiProvider, setSelectedAiProvider] = useState<"gemini" | "groq" | "openai">(
    aiConfig.provider || "gemini"
  );
  const [aiApiKeyInput, setAiApiKeyInput] = useState(aiConfig.apiKey || "");
  const [showAiKey, setShowAiKey] = useState(false);
  const [aiTesting, setAiTesting] = useState(false);
  const [aiTestResult, setAiTestResult] = useState<{
    valid: boolean;
    message?: string;
    error?: string;
  } | null>(null);

  const handleTestAndSaveAi = async () => {
    if (!aiApiKeyInput.trim()) {
      setAiTestResult({ valid: false, error: "Ingresa una clave API antes de probar." });
      return;
    }
    setAiTesting(true);
    setAiTestResult(null);
    try {
      const res = await fetch("/api/ai-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: selectedAiProvider,
          apiKey: aiApiKeyInput.trim(),
        }),
      });
      const data = await res.json();
      if (res.ok && data.valid) {
        setAiConfig({
          provider: selectedAiProvider,
          apiKey: aiApiKeyInput.trim(),
          model: data.model || (selectedAiProvider === "gemini" ? "gemini-3.8-flash" : "default"),
          isConnected: true,
        });
        setAiTestResult({
          valid: true,
          message: data.message || `Conexión exitosa con ${data.model}`,
        });
        setTimeout(() => {
          setActiveModal("none");
        }, 1200);
      } else {
        setAiTestResult({
          valid: false,
          error: data.error || "No se pudo validar la clave API con el proveedor seleccionado.",
        });
      }
    } catch (err: any) {
      setAiTestResult({
        valid: false,
        error: `Error de red: ${err.message}`,
      });
    } finally {
      setAiTesting(false);
    }
  };

  const handleDisconnectAi = () => {
    setAiConfig({
      provider: "gemini",
      apiKey: "",
      model: "gemini-3.8-flash",
      isConnected: false,
    });
    setAiApiKeyInput("");
    setAiTestResult(null);
  };

  if (!activeModal || activeModal === "none") return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150"
      onClick={() => setActiveModal("none")}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-float"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ================================================================= */}
        {/* 1. QUICK SEARCH MODAL (⌘K)                                        */}
        {/* ================================================================= */}
        {activeModal === "search" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
              <div className="flex items-center gap-2 text-sm font-bold">
                <Search className="h-4 w-4 text-[var(--primary)]" />
                <span>Búsqueda Rápida</span>
              </div>
              <button
                onClick={() => setActiveModal("none")}
                className="rounded-lg p-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="relative">
              <input
                type="text"
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar por título de video o palabras en transcripción..."
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3.5 py-2.5 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
              />
            </div>

            <div className="max-h-64 overflow-y-auto space-y-1.5 pt-1">
              {projects
                .filter(
                  (p) =>
                    !searchQuery.trim() ||
                    p.title.toLowerCase().includes(searchQuery.toLowerCase())
                )
                .slice(0, 5)
                .map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      setActiveModal("none");
                      router.push(`/clip/${p.id}`);
                    }}
                    className="w-full flex items-center justify-between rounded-xl p-2.5 text-left text-xs hover:bg-[var(--secondary)] transition group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Film className="h-4 w-4 text-[var(--muted-foreground)] shrink-0" />
                      <div className="truncate">
                        <div className="font-semibold text-[var(--foreground)] truncate">
                          {p.title}
                        </div>
                        <div className="text-[11px] text-[var(--muted-foreground)]">
                          {p.clipCount} clips generados
                        </div>
                      </div>
                    </div>
                    <ArrowRight className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 transition text-[var(--primary)]" />
                  </button>
                ))}

              {projects.length === 0 && (
                <div className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                  No hay proyectos creados aún.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* 2. AI CONNECTION MODAL (Google Gemini / Groq / OpenAI)             */}
        {/* ================================================================= */}
        {activeModal === "ai-connect" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--primary-subtle)] text-[var(--primary)]">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--foreground)]">
                    Motor de Inteligencia Artificial
                  </h3>
                  <p className="text-[11px] text-[var(--muted-foreground)]">
                    Conecta tu clave API local para curación multimodal y detección de momentos virales
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveModal("none")}
                className="rounded-lg p-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Provider Selector Tabs */}
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  { id: "gemini", label: "Google Gemini", note: "Gratuito y Rápido" },
                  { id: "groq", label: "Groq Cloud", note: "Llama 3.3 70B" },
                  { id: "openai", label: "OpenAI", note: "GPT-4o Mini" },
                ] as const
              ).map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setSelectedAiProvider(p.id);
                    setAiTestResult(null);
                  }}
                  className={`rounded-xl border p-2.5 text-center transition cursor-pointer ${
                    selectedAiProvider === p.id
                      ? "border-[var(--primary)] bg-[var(--primary-subtle)]"
                      : "border-[var(--border)] bg-[var(--secondary)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div
                    className={`text-xs font-bold ${
                      selectedAiProvider === p.id
                        ? "text-[var(--primary)]"
                        : "text-[var(--foreground)]"
                    }`}
                  >
                    {p.label}
                  </div>
                  <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                    {p.note}
                  </div>
                </button>
              ))}
            </div>

            {/* Key Input Field */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <label className="font-semibold text-[var(--foreground)]">
                  Clave API ({selectedAiProvider.toUpperCase()})
                </label>
                <a
                  href={
                    selectedAiProvider === "gemini"
                      ? "https://aistudio.google.com/app/apikey"
                      : selectedAiProvider === "groq"
                      ? "https://console.groq.com/keys"
                      : "https://platform.openai.com/api-keys"
                  }
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-[var(--primary)] hover:underline"
                >
                  <span>Obtener clave gratis</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>

              <div className="relative">
                <input
                  type={showAiKey ? "text" : "password"}
                  value={aiApiKeyInput}
                  onChange={(e) => setAiApiKeyInput(e.target.value)}
                  placeholder={
                    selectedAiProvider === "gemini"
                      ? "AIzaSy..."
                      : selectedAiProvider === "groq"
                      ? "gsk_..."
                      : "sk-proj-..."
                  }
                  className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] pl-3.5 pr-10 py-2 text-xs font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowAiKey(!showAiKey)}
                  className="absolute right-3 top-2.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  {showAiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Test Result Feedback */}
            {aiTestResult && (
              <div
                className={`flex items-start gap-2 rounded-xl p-3 text-xs ${
                  aiTestResult.valid
                    ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : "border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300"
                }`}
              >
                {aiTestResult.valid ? (
                  <Check className="h-4 w-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                )}
                <span>{aiTestResult.message || aiTestResult.error}</span>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              {aiConfig.isConnected ? (
                <button
                  type="button"
                  onClick={handleDisconnectAi}
                  className="rounded-xl border border-red-500/30 px-3 py-1.5 text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-500/10 transition cursor-pointer"
                >
                  Desconectar
                </button>
              ) : (
                <span className="text-[11px] text-[var(--muted-foreground)]">
                  Se guarda únicamente en el navegador (local)
                </span>
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveModal("none")}
                  className="rounded-xl border border-[var(--border)] px-3 py-1.5 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
                >
                  Cerrar
                </button>
                <button
                  type="button"
                  onClick={handleTestAndSaveAi}
                  disabled={aiTesting || !aiApiKeyInput.trim()}
                  className="rounded-xl bg-[var(--primary)] px-4 py-1.5 text-xs font-bold text-white hover:opacity-95 transition disabled:opacity-50 cursor-pointer shadow-xs"
                >
                  {aiTesting ? "Probando..." : "Probar y Guardar"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
