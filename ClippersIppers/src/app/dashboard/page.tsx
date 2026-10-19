"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import {
  activeModalAtom,
  aiConfigAtom,
  clipsAtom,
  draftSubmissionAtom,
  projectsAtom,
  selectedBrandTemplateIdAtom,
} from "@/store/opusStore";
import { AspectRatioOption, ClipProject } from "@/types/opus";
import {
  extractLocalVideoMetadata,
  fetchLiveMediaMetadata,
  formatSecondsToTimecode,
} from "@/lib/multipartUploader";
import {
  Sparkles,
  Upload,
  Link2,
  Film,
  Play,
  Scissors,
  Trash2,
  ArrowRight,
  SlidersHorizontal,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
} from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useAtom(projectsAtom);
  const [clips, setClips] = useAtom(clipsAtom);
  const [draft, setDraft] = useAtom(draftSubmissionAtom);
  const [aiConfig] = useAtom(aiConfigAtom);
  const [, setActiveModal] = useAtom(activeModalAtom);
  const [selectedBrandId] = useAtom(selectedBrandTemplateIdAtom);

  const [urlInput, setUrlInput] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);
  const [livePreview, setLivePreview] = useState<any>(null);
  const [selectedAspect, setSelectedAspect] = useState<AspectRatioOption>("9:16");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [clipLength, setClipLength] = useState("Auto (<90s)");
  const [topicPrompt, setTopicPrompt] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Debounced URL inspection for real YouTube or media metadata
  useEffect(() => {
    const trimmed = urlInput.trim();
    if (!trimmed || !trimmed.startsWith("http")) {
      setLivePreview(null);
      return;
    }

    const timer = setTimeout(async () => {
      setIsInspecting(true);
      try {
        const info = await fetchLiveMediaMetadata(trimmed);
        if (info.valid) {
          setLivePreview(info);
          setUrlError(null);
        } else {
          setLivePreview(null);
        }
      } catch {
        setLivePreview(null);
      } finally {
        setIsInspecting(false);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [urlInput]);

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.trim()) {
        setUrlInput(text.trim());
      }
    } catch {
      // Fallback
    }
  };

  const handleLocalFileSelect = async (file: File) => {
    setUrlError(null);
    setIsInspecting(true);
    try {
      const meta = await extractLocalVideoMetadata(file);
      setLivePreview({
        valid: true,
        sourceUrl: `local://${file.name}`,
        title: meta.title,
        platform: "LOCAL",
        durationSec: meta.durationSec,
        resolution: meta.resolution,
        thumbnailUrl: meta.thumbnailDataUrl,
        localObjectUrl: meta.objectUrl,
      });
      setUrlInput(`local://${file.name}`);
    } catch (err: any) {
      setUrlError(`No se pudo procesar el archivo local: ${err.message}`);
    } finally {
      setIsInspecting(false);
    }
  };

  // Direct 1-Click Generation Flow (Local, Fast, Unlimited)
  const handleStartGeneration = async () => {
    const targetUrl = urlInput.trim();
    if (!targetUrl && !livePreview) {
      setUrlError("Pega un enlace de YouTube o selecciona un video local para comenzar.");
      return;
    }

    setIsGenerating(true);
    setGenerationProgress("Inspeccionando video y preparando flujo de trabajo...");

    let info = livePreview;
    if (!info || info.sourceUrl !== targetUrl) {
      info = await fetchLiveMediaMetadata(targetUrl);
    }

    if (!info?.valid) {
      setUrlError(info?.errorMessage || "No se pudo obtener información del video.");
      setIsGenerating(false);
      setGenerationProgress(null);
      return;
    }

    const durationSec = Math.max(15, info.durationSec || 300);
    const newProjectId = `proj-${Date.now().toString().slice(-6)}`;
    const finalTitle = info.title || info.suggestedTitle || "Video Clip";

    // Set draft state
    setDraft((prev) => ({
      ...prev,
      sourceUrl: targetUrl,
      title: finalTitle,
      platform: info.platform || "YOUTUBE",
      durationSec,
      resolution: info.resolution || "1080p",
      thumbnailUrl: info.thumbnailUrl,
      localObjectUrl: info.localObjectUrl,
      rangeStartSec: 0,
      rangeEndSec: durationSec,
      aspectRatio: selectedAspect,
      brandTemplateId: selectedBrandId,
      customPrompt: topicPrompt,
      workflowId: "builtin:agent",
      autoEditMode: true,
      keywords: info.keywords || ["viral", "shorts"],
      model: "ClipAnything",
      layoutMode: "fill",
      enableCaptions: true,
      enableAutoHook: true,
      enableEmojis: true,
      removeFillerWords: true,
      removePauses: true,
      brollType: "none",
      enableSpeechEnhance: false,
      enableUpscale: false,
      enableDubbing: false,
      clipLengths: [clipLength],
    }));

    setGenerationProgress("Extrayendo transcripción real palabra por palabra y flujo MP4...");

    // Call /api/ai-curate
    try {
      const curateRes = await fetch("/api/ai-curate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: aiConfig.isConnected ? aiConfig.provider : "local",
          apiKey: aiConfig.isConnected ? aiConfig.apiKey : "",
          videoData: {
            url: targetUrl,
            title: finalTitle,
            author: info.author || "",
            durationSec,
            keywords: info.keywords || [],
            customPrompt: topicPrompt,
            modelChoice: "ClipAnything",
            aspectRatio: selectedAspect,
          },
        }),
      });

      const curateData = await curateRes.json();
      let generatedClips: any[] = [];

      if (curateRes.ok && curateData.success && Array.isArray(curateData.clips) && curateData.clips.length > 0) {
        generatedClips = curateData.clips.map((c: any) => ({
          clipId: `clip-${newProjectId}-${c.rank}`,
          projectId: newProjectId,
          rank: c.rank,
          title: c.title,
          viralityScore: c.viralityScore,
          scoreBreakdown: c.scoreBreakdown,
          viralityExplanation: c.viralityExplanation,
          duration: c.duration,
          startSec: c.startSec,
          endSec: c.endSec,
          aspectRatio: selectedAspect,
          layoutMode: "fill",
          transcriptWords: c.transcriptWords,
          like: c.rank === 1,
          dislike: false,
          isEdited: false,
          hasAutoHook: true,
          hookText: c.hookText,
          brollSegments: [],
          captionPresetId: selectedBrandId,
          keywords: info.keywords || ["viral"],
          videoUrl: info.localObjectUrl || c.videoStreamUrl || curateData.videoStreamUrl,
          thumbnailUrl: info.thumbnailUrl,
          cropX: 50,
          zoom: 1,
        }));
      }

      // Create new project in local storage
      const newProject: ClipProject = {
        id: newProjectId,
        projectId: newProjectId,
        title: finalTitle,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        stage: "COMPLETE",
        progress: 1,
        sourceInfo: {
          title: finalTitle,
          type: info.platform || "YOUTUBE",
          videoUrl: targetUrl,
          thumbnailUrl: info.thumbnailUrl,
          durationMs: durationSec * 1000,
          resolution: info.resolution || "1080p",
          language: "es",
        },
        productTier: "PRO",
        clipCount: generatedClips.length,
        isPrivate: true,
        storageStatus: "PERMANENT",
        storageExpireAt: "",
        collectionIds: [],
        workflowId: "builtin:agent",
        brandTemplateId: selectedBrandId,
        curationPref: {
          model: "ClipAnything",
          genre: "Auto",
          clipLengths: [clipLength],
          customPrompt: topicPrompt,
          keywords: info.keywords || [],
          rangeStartSec: 0,
          rangeEndSec: durationSec,
          skipSlicing: false,
        },
        renderPref: {
          enableCaptions: true,
          enableAutoHook: true,
          enableEmojis: true,
          removeFillerWords: true,
          removePauses: true,
          brollType: "none",
          enableSpeechEnhance: false,
          enableUpscale: false,
          aspectRatio: selectedAspect,
          layoutMode: "fill",
        },
        creditsCharged: 0,
        creditsFrozen: 0,
      };

      setProjects((prev) => [newProject, ...prev]);
      setClips((prev) => [...prev, ...generatedClips]);

      // Route straight to clip results
      router.push(`/clip/${newProjectId}`);
    } catch (err: any) {
      setUrlError(`Error procesando clips: ${err.message}`);
      setIsGenerating(false);
      setGenerationProgress(null);
    }
  };

  const handleDeleteProject = (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
    setClips((prev) => prev.filter((c) => c.projectId !== projectId));
  };

  const filteredProjects = projects.filter((p) =>
    projectSearch.trim()
      ? p.title.toLowerCase().includes(projectSearch.toLowerCase())
      : true
  );

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-12">
      {/* 1. Creative Welcome Area */}
      <div className="text-center space-y-3 max-w-2xl mx-auto">
        <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-[var(--foreground)]">
          Crea clips virales con{" "}
          <span className="text-[var(--primary)] inline-block">inteligencia artificial</span>
        </h1>
        <p className="text-sm sm:text-base text-[var(--muted-foreground)] leading-relaxed">
          Pega un enlace de YouTube o arrastra un video local. La IA extrae el audio real
          palabra por palabra y detecta los mejores momentos automáticamente.
        </p>
      </div>

      {/* 2. Hero Generator Box (Minimalist, Clean, Linear / Apple Style) */}
      <div className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 sm:p-7 shadow-card space-y-5">
        {/* URL Input Bar */}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            <div className="relative flex-1">
              <div className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-[var(--muted-foreground)]">
                <Link2 className="h-4 w-4" />
              </div>
              <input
                type="text"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="Pega un enlace de YouTube (ej. https://www.youtube.com/watch?v=...)"
                disabled={isGenerating}
                className="w-full rounded-2xl border border-[var(--border)] bg-[var(--secondary)] pl-10 pr-20 py-3 text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)] focus:bg-[var(--card)] focus:outline-none transition"
              />
              <button
                type="button"
                onClick={handlePasteFromClipboard}
                className="absolute right-2.5 top-2.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
              >
                Pegar
              </button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleLocalFileSelect(f);
              }}
            />

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isGenerating}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm font-semibold text-[var(--foreground)] hover:bg-[var(--secondary)] transition cursor-pointer shrink-0"
            >
              <Upload className="h-4 w-4 text-[var(--muted-foreground)]" />
              <span>Subir Archivo</span>
            </button>
          </div>

          {urlError && (
            <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{urlError}</span>
            </div>
          )}
        </div>

        {/* Live Detected Video Preview Card */}
        {livePreview && (
          <div className="flex flex-col sm:flex-row items-center gap-4 rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-3.5 transition">
            <img
              src={livePreview.thumbnailUrl}
              alt={livePreview.title}
              className="h-20 w-32 rounded-xl object-cover border border-black/10 shrink-0"
            />
            <div className="flex-1 min-w-0 text-center sm:text-left space-y-1">
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
                <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase">
                  {livePreview.platform} · {livePreview.resolution}
                </span>
                <span className="text-xs text-[var(--muted-foreground)] font-mono">
                  {formatSecondsToTimecode(livePreview.durationSec)}
                </span>
              </div>
              <h3 className="text-sm font-bold text-[var(--foreground)] truncate">
                {livePreview.title}
              </h3>
            </div>
          </div>
        )}

        {/* Aspect Ratio Selector + Quick Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1 border-t border-[var(--border)]">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-[var(--muted-foreground)]">
              Formato:
            </span>
            <div className="flex items-center rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-0.5">
              {(
                [
                  { id: "9:16", label: "9:16 Vertical (Shorts/TikTok)" },
                  { id: "16:9", label: "16:9 Horizontal" },
                  { id: "1:1", label: "1:1 Cuadrado" },
                ] as const
              ).map((ar) => (
                <button
                  key={ar.id}
                  type="button"
                  onClick={() => setSelectedAspect(ar.id)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                    selectedAspect === ar.id
                      ? "bg-[var(--card)] text-[var(--foreground)] shadow-xs"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {ar.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer self-start sm:self-auto"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>{showAdvanced ? "Ocultar opciones" : "Más opciones"}</span>
          </button>
        </div>

        {/* Collapsible Clean Options */}
        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/40 p-4 animate-in fade-in duration-150">
            <div>
              <label className="block text-xs font-semibold text-[var(--foreground)] mb-1">
                Duración deseada de clips
              </label>
              <select
                value={clipLength}
                onChange={(e) => setClipLength(e.target.value)}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-medium text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
              >
                <option value="Auto (<90s)">Automático (&lt;90s)</option>
                <option value="<30s">Corto (&lt;30s)</option>
                <option value="30s~60s">Medio (30s a 60s)</option>
                <option value="60s~90s">Largo (60s a 90s)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[var(--foreground)] mb-1">
                Enfoque o tema (Prompt opcional)
              </label>
              <input
                type="text"
                value={topicPrompt}
                onChange={(e) => setTopicPrompt(e.target.value)}
                placeholder="Ej: Momentos más divertidos, consejos clave..."
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)] focus:outline-none"
              />
            </div>
          </div>
        )}

        {/* Primary Generation CTA */}
        <div className="pt-2">
          <button
            type="button"
            onClick={handleStartGeneration}
            disabled={isGenerating || (!urlInput.trim() && !livePreview)}
            className="w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-[var(--primary)] px-6 py-3.5 text-sm font-bold text-white shadow-xs hover:opacity-95 transition disabled:opacity-50 cursor-pointer"
          >
            <Sparkles className="h-4 w-4" />
            <span>
              {isGenerating
                ? generationProgress || "Generando clips..."
                : "Generar Clips con IA"}
            </span>
          </button>
        </div>
      </div>

      {/* 3. Recent Projects List */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-[var(--foreground)]">
              Tus Proyectos
            </h2>
            <span className="rounded-full bg-[var(--secondary)] px-2 py-0.5 text-xs font-semibold text-[var(--muted-foreground)]">
              {projects.length}
            </span>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              type="text"
              value={projectSearch}
              onChange={(e) => setProjectSearch(e.target.value)}
              placeholder="Buscar proyecto..."
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] pl-8 pr-3 py-1.5 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
            />
          </div>
        </div>

        {filteredProjects.length === 0 ? (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-12 text-center space-y-2">
            <Film className="h-8 w-8 text-[var(--muted-foreground)] mx-auto opacity-50" />
            <div className="text-sm font-bold text-[var(--foreground)]">
              No hay proyectos todavía
            </div>
            <p className="text-xs text-[var(--muted-foreground)] max-w-sm mx-auto">
              Pega un enlace de YouTube arriba para generar tu primer conjunto de clips
              con subtítulos sincronizados.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredProjects.map((p) => {
              const projectClips = clips.filter((c) => c.projectId === p.id);
              const durationSec = Math.round((p.sourceInfo.durationMs || 0) / 1000);

              return (
                <div
                  key={p.id}
                  onClick={() => router.push(`/clip/${p.id}`)}
                  className="group rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden hover:border-[var(--primary)]/60 hover:shadow-card transition flex flex-col justify-between cursor-pointer"
                >
                  <div className="relative aspect-video bg-black/10 overflow-hidden">
                    <img
                      src={p.sourceInfo.thumbnailUrl}
                      alt={p.title}
                      className="h-full w-full object-cover group-hover:scale-103 transition duration-300"
                    />
                    <div className="absolute bottom-2 right-2 rounded-md bg-black/80 backdrop-blur-xs px-2 py-0.5 text-[10px] font-mono text-white">
                      {formatSecondsToTimecode(durationSec)}
                    </div>
                  </div>

                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5 text-[11px] text-[var(--muted-foreground)]">
                        <span className="font-semibold text-[var(--primary)]">
                          {p.clipCount || projectClips.length} clips
                        </span>
                        <span>·</span>
                        <span>{p.sourceInfo.type}</span>
                      </div>
                      <h3 className="text-xs sm:text-sm font-bold text-[var(--foreground)] line-clamp-2">
                        {p.title}
                      </h3>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
                      <span className="text-[11px] font-semibold text-[var(--primary)] group-hover:underline">
                        Ver clips →
                      </span>
                      <button
                        onClick={(e) => handleDeleteProject(p.id, e)}
                        className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:text-red-500 hover:bg-red-500/10 transition"
                        title="Eliminar proyecto"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
