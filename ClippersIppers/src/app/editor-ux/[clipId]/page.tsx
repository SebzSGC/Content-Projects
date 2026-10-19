"use client";

import React, { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import {
  brandTemplatesAtom,
  clipsAtom,
  projectsAtom,
} from "@/store/opusStore";
import {
  AspectRatioOption,
  LayoutModeOption,
  TranscriptWord,
} from "@/types/opus";
import { formatSecondsToTimecode } from "@/lib/multipartUploader";
import { getCleanVisibleWords, getNaturalSubtitlePhrase } from "@/lib/transcriptUtils";
import { exportAndDownloadClip, ClipExportProgress } from "@/lib/clipExporter";
import {
  ArrowLeft,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Scissors,
  Sparkles,
  Captions,
  Film,
  Volume2,
  VolumeX,
  Download,
  Check,
  Trash2,
  Plus,
  Grid,
  Move,
  Highlighter,
  Type,
  Wand2,
  ZoomIn,
  SlidersHorizontal,
  RefreshCw,
} from "lucide-react";

function extractYouTubeId(url?: string, thumb?: string): string | null {
  const fromUrl = url?.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/)?.[1];
  if (fromUrl) return fromUrl;
  const fromThumb = thumb?.match(/\/vi(?:_webp)?\/([a-zA-Z0-9_-]{11})\//)?.[1];
  return fromThumb || null;
}

export default function NleEditorPage({
  params,
}: {
  params: Promise<{ clipId: string }>;
}) {
  const { clipId } = use(params);
  const router = useRouter();
  const [clips, setClips] = useAtom(clipsAtom);
  const [projects] = useAtom(projectsAtom);
  const [brandTemplates, setBrandTemplates] = useAtom(brandTemplatesAtom);

  const clip = clips.find((c) => c.clipId === clipId) || clips[0];
  const project = projects.find((p) => p.id === clip?.projectId);

  const activeTemplate =
    brandTemplates.find((bt) => bt.id === clip.captionPresetId) ||
    brandTemplates[0];

  const ytId = extractYouTubeId(
    project?.sourceInfo?.videoUrl,
    clip?.thumbnailUrl || project?.sourceInfo?.thumbnailUrl
  );

  const resolvedStreamUrl =
    clip.videoUrl || (ytId ? `/api/video-stream?videoId=${ytId}` : undefined);

  // Editor state
  const [leftTab, setLeftTab] = useState<"transcript" | "captions" | "broll" | "hook">(
    "transcript"
  );
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [playheadSec, setPlayheadSec] = useState(0);
  const [selectedWordId, setSelectedWordId] = useState<string>(
    clip.transcriptWords[0]?.id || "w-0"
  );
  const [editingWordText, setEditingWordText] = useState<string>(
    clip.transcriptWords[0]?.word || ""
  );
  const [showMoveableBox, setShowMoveableBox] = useState(true);
  const [showSafeGrid, setShowSafeGrid] = useState(false);
  const [faceFocusMode, setFaceFocusMode] = useState<"speaker" | "screen">("speaker");
  const [timelineZoom, setTimelineZoom] = useState(100);
  const [editorToast, setEditorToast] = useState<string | null>(null);
  const [isDraggingCrop, setIsDraggingCrop] = useState(false);
  const [autoZoomEnabled, setAutoZoomEnabled] = useState(true);
  const [autoReframeEnabled, setAutoReframeEnabled] = useState(true);
  const [isExportingClip, setIsExportingClip] = useState(false);
  const [exportProgress, setExportProgress] = useState<ClipExportProgress | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const splitVideoRef = useRef<HTMLVideoElement | null>(null);
  const dragStartXRef = useRef<number>(0);
  const dragStartCropXRef = useRef<number>(50);
  const dragDistanceRef = useRef<number>(0);

  const maxClipTime = Math.max(
    5,
    clip.duration ||
      clip.transcriptWords[clip.transcriptWords.length - 1]?.end ||
      30
  );

  const cropX = clip.cropX ?? 50;
  const zoom = clip.zoom ?? 1;

  // Seek helper that updates both HTML5 video and playhead state
  const seekToRelativeSecond = (relSec: number, autoPlay = false) => {
    const clamped = Math.max(0, Math.min(maxClipTime, Number(relSec.toFixed(2))));
    setPlayheadSec(clamped);
    const v = videoRef.current;
    if (v) {
      v.currentTime = clip.startSec + clamped;
      if (autoPlay) {
        v.play().catch(() => {});
        setIsPlaying(true);
      }
    }
    if (splitVideoRef.current) {
      splitVideoRef.current.currentTime = clip.startSec + clamped;
    }
  };

  const handleTogglePlay = () => {
    const v = videoRef.current;
    if (!v) {
      setIsPlaying((p) => !p);
      return;
    }
    if (isPlaying) {
      v.pause();
      splitVideoRef.current?.pause();
      setIsPlaying(false);
    } else {
      if (v.currentTime < clip.startSec || v.currentTime >= clip.endSec) {
        v.currentTime = clip.startSec + playheadSec;
      }
      v.play().catch(() => {});
      splitVideoRef.current?.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  // Fallback timer ONLY for demo projects that don't have a real video stream
  useEffect(() => {
    if (!isPlaying || resolvedStreamUrl) return;
    const interval = setInterval(() => {
      setPlayheadSec((prev) => {
        const next = Number((prev + 0.12).toFixed(2));
        return next >= maxClipTime ? 0 : next;
      });
    }, 120);
    return () => clearInterval(interval);
  }, [isPlaying, maxClipTime, resolvedStreamUrl]);

  const selectedWord =
    clip.transcriptWords.find((w) => w.id === selectedWordId) ||
    clip.transcriptWords[0];

  // Natural coherent subtitle phrase (avoids gluing words from 5s ahead or across pauses)
  const visibleWords = getCleanVisibleWords(clip.transcriptWords);
  const activeWordIdx = visibleWords.findIndex(
    (w) => playheadSec >= w.start - 0.05 && playheadSec <= w.end + 0.15
  );
  const phraseWords =
    activeWordIdx >= 0
      ? getNaturalSubtitlePhrase(visibleWords, activeWordIdx, playheadSec)
      : [];

  const activeWord = activeWordIdx >= 0 ? visibleWords[activeWordIdx] : null;
  const isHookMoment = isPlaying && playheadSec < 3.2 && clip.hasAutoHook;
  const isPunchlineMoment =
    isPlaying &&
    Boolean(
      activeWord?.highlight === "color1" ||
        activeWord?.highlight === "color2" ||
        activeWord?.emoji
    );

  const dynamicZoom = autoZoomEnabled
    ? zoom * (isPunchlineMoment ? 1.18 : isHookMoment ? 1.12 : 1.0)
    : zoom;

  let dynamicCropX = cropX;
  if (autoReframeEnabled && clip.aspectRatio === "9:16") {
    if (activeWord?.speaker === "Speaker 2") {
      dynamicCropX = 66;
    } else if (activeWord?.speaker === "Speaker 1") {
      dynamicCropX = 36;
    } else if (activeWordIdx >= 0) {
      dynamicCropX = activeWordIdx % 2 === 0 ? 48 : 52;
    }
  }

  const updateClipWords = (updater: (words: TranscriptWord[]) => TranscriptWord[]) => {
    setClips((prev) =>
      prev.map((c) =>
        c.clipId === clip.clipId
          ? { ...c, isEdited: true, transcriptWords: updater(c.transcriptWords) }
          : c
      )
    );
  };

  const updateClipProps = (patch: Partial<typeof clip>) => {
    setClips((prev) =>
      prev.map((c) =>
        c.clipId === clip.clipId ? { ...c, ...patch, isEdited: true } : c
      )
    );
  };

  const handleSelectWord = (word: TranscriptWord) => {
    setSelectedWordId(word.id);
    setEditingWordText(word.word);
    seekToRelativeSecond(word.start, false);
  };

  const handleSaveWordText = () => {
    if (!editingWordText.trim()) return;
    updateClipWords((words) =>
      words.map((w) =>
        w.id === selectedWordId ? { ...w, word: editingWordText.trim() } : w
      )
    );
    setEditorToast(
      `Palabra actualizada a "${editingWordText.trim()}" en la pista de subtítulos.`
    );
    setTimeout(() => setEditorToast(null), 2500);
  };

  const handleCycleWordHighlight = (wordId: string) => {
    updateClipWords((words) =>
      words.map((w) => {
        if (w.id !== wordId) return w;
        const nextHighlight =
          w.highlight === "none"
            ? "color1"
            : w.highlight === "color1"
            ? "color2"
            : "none";
        return { ...w, highlight: nextHighlight };
      })
    );
  };

  const handleToggleWordDelete = (wordId: string) => {
    updateClipWords((words) =>
      words.map((w) => (w.id === wordId ? { ...w, deleted: !w.deleted } : w))
    );
    setEditorToast(
      "Corte por texto actualizado: el reproductor saltará automáticamente las palabras recortadas."
    );
    setTimeout(() => setEditorToast(null), 2500);
  };

  const handleStripAllFillersAndPauses = () => {
    const fillerSet = new Set(["eh", "um", "uh", "este", "bueno", "osea", "pues"]);
    updateClipWords((words) =>
      words.map((w) => {
        const clean = w.word.toLowerCase().replace(/[.,!?¿¡]/g, "");
        return w.isFiller || w.isPause || fillerSet.has(clean)
          ? { ...w, deleted: true }
          : w;
      })
    );
    setEditorToast(
      "Muletillas y pausas marcadas como recortadas: el video las saltará durante la reproducción."
    );
    setTimeout(() => setEditorToast(null), 3000);
  };

  const handleAddBrollSegment = (type: "stock" | "ai_video") => {
    const newSeg = {
      id: `br-${Date.now()}`,
      type,
      label:
        type === "ai_video"
          ? "AI Video B-Roll: Neural Cutaway"
          : "Stock B-Roll: Reaction Clip",
      startSec: Math.min(maxClipTime - 3, Math.max(0, Math.round(playheadSec))),
      endSec: Math.min(maxClipTime, Math.round(playheadSec) + 4),
      thumbnailUrl: clip.thumbnailUrl,
      creditCost: 0,
    };

    updateClipProps({
      brollSegments: [...clip.brollSegments, newSeg],
    });

    setEditorToast(
      type === "ai_video"
        ? "Segmento AI Video B-Roll insertado en la pista 3."
        : "Segmento Stock B-Roll insertado en la pista 3."
    );
    setTimeout(() => setEditorToast(null), 3000);
  };

  const handleDownloadCurrentClip = async () => {
    const resolvedVideoId =
      ytId ||
      extractYouTubeId(resolvedStreamUrl || "") ||
      extractYouTubeId(clip.videoUrl || "") ||
      extractYouTubeId(clip.thumbnailUrl || "");

    if (!resolvedStreamUrl && !resolvedVideoId) {
      setEditorToast("No hay flujo de video disponible para exportar.");
      return;
    }

    setIsExportingClip(true);
    setExportProgress({
      status: "preparing",
      progress: 10,
      message: "Iniciando exportación Full HD de clip con subtítulos...",
    });

    try {
      await exportAndDownloadClip({
        videoUrl: resolvedStreamUrl || `/api/video-stream?videoId=${resolvedVideoId}`,
        videoId: resolvedVideoId || undefined,
        startSec: clip.startSec,
        endSec: clip.endSec,
        title: clip.title,
        transcriptWords: clip.transcriptWords,
        aspectRatio: clip.aspectRatio,
        cropX: cropX,
        zoom: zoom,
        hookText: clip.hasAutoHook ? clip.hookText : undefined,
        burnSubtitles: true,
        onProgress: (p) => setExportProgress(p),
      });
      setEditorToast("¡Clip Full HD descargado con éxito!");
    } catch (err: any) {
      setEditorToast(`Error al descargar clip: ${err?.message || "Desconocido"}`);
    } finally {
      setTimeout(() => {
        setIsExportingClip(false);
        setExportProgress(null);
      }, 2000);
    }
  };

  const handleExportEditedJson = () => {
    const payload = JSON.stringify(
      { clip, brandTemplate: activeTemplate },
      null,
      2
    );
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${clip.clipId}-nle-project.json`;
    a.click();
    URL.revokeObjectURL(url);
    setEditorToast("Proyecto NLE guardado y exportado como JSON local.");
    setTimeout(() => setEditorToast(null), 3000);
  };

  const activeBrollAtPlayhead = clip.brollSegments.find(
    (b) => playheadSec >= b.startSec && playheadSec <= b.endSec
  );

  const deletedWordsCount = clip.transcriptWords.filter((w) => w.deleted).length;

  return (
    <div className="flex flex-col h-[calc(100vh-60px)] bg-[var(--background)] text-[var(--foreground)] overflow-hidden">
      {/* Top NLE Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--card)] px-4 py-2.5 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => router.push(`/clip/${clip.projectId}`)}
            className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
            title="Volver a resultados del proyecto"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded bg-[var(--primary-subtle)] px-2 py-0.5 text-[10px] font-bold text-[var(--primary)] border border-[var(--primary-subtle-border)]">
                Score {clip.viralityScore}
              </span>
              <span className="text-xs font-bold truncate text-[var(--foreground)]">{clip.title}</span>
              <span className="hidden md:inline-block text-[11px] font-mono text-[var(--muted-foreground)]">
                ({formatSecondsToTimecode(clip.startSec)} –{" "}
                {formatSecondsToTimecode(clip.endSec)})
              </span>
            </div>
          </div>
        </div>

        {/* Aspect Ratio & Layout Mode Selector */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-0.5">
            {(["9:16", "16:9", "1:1", "4:5"] as AspectRatioOption[]).map((ar) => (
              <button
                key={ar}
                onClick={() => updateClipProps({ aspectRatio: ar })}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition cursor-pointer ${
                  clip.aspectRatio === ar
                    ? "bg-[var(--primary)] text-black"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                }`}
              >
                {ar}
              </button>
            ))}
          </div>

          <div className="hidden sm:flex items-center rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-0.5">
            {(["fill", "fit", "split"] as LayoutModeOption[]).map((lm) => (
              <button
                key={lm}
                onClick={() => updateClipProps({ layoutMode: lm })}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition cursor-pointer ${
                  clip.layoutMode === lm
                    ? "bg-[var(--card)] text-[var(--primary)] border border-[var(--primary)]/40"
                    : "text-[var(--muted-foreground)]"
                }`}
              >
                {lm}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowMoveableBox(!showMoveableBox)}
            className={`inline-flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs font-semibold transition cursor-pointer ${
              showMoveableBox
                ? "border-sky-400/50 bg-sky-500/15 text-sky-300"
                : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)]"
            }`}
            title="Mostrar/ocultar caja de encuadre IA"
          >
            <Move className="h-3.5 w-3.5" />
            <span className="hidden md:inline">Crop Box</span>
          </button>

          <button
            onClick={() => setShowSafeGrid(!showSafeGrid)}
            className={`inline-flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs font-semibold transition cursor-pointer ${
              showSafeGrid
                ? "border-sky-400/50 bg-sky-500/15 text-sky-300"
                : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)]"
            }`}
            title="Mostrar/ocultar guías de composición TikTok/Shorts"
          >
            <Grid className="h-3.5 w-3.5" />
            <span className="hidden md:inline">Safe Grid</span>
          </button>

          <button
            onClick={handleDownloadCurrentClip}
            disabled={isExportingClip}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--primary)] bg-[var(--primary)]/15 px-3 py-1.5 text-xs font-bold text-[var(--primary)] hover:bg-[var(--primary)] hover:text-white transition cursor-pointer disabled:opacity-50"
            title="Descargar exactamente este clip recortado (9:16 con subtítulos)"
          >
            {isExportingClip ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span>{exportProgress?.progress || 0}%</span>
              </>
            ) : (
              <>
                <Download className="h-3.5 w-3.5" />
                <span>Descargar Clip</span>
              </>
            )}
          </button>

          {ytId && (
            <a
              href={`/api/video-stream?videoId=${ytId}&download=1`}
              download={`${clip.clipId}-full.mp4`}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-2.5 py-1.5 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition"
              title="Descargar video original completo"
            >
              <Download className="h-3.5 w-3.5 opacity-60" />
              <span className="hidden sm:inline">Video Completo</span>
            </a>
          )}

          <button
            onClick={handleExportEditedJson}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-black hover:opacity-95 transition cursor-pointer"
          >
            <Check className="h-3.5 w-3.5" />
            <span>Guardar Proyecto</span>
          </button>
        </div>
      </div>

      {editorToast && (
        <div className="bg-emerald-500/15 border-b border-emerald-500/40 px-4 py-1.5 text-xs text-emerald-300 flex items-center gap-2 shrink-0">
          <Check className="h-3.5 w-3.5" />
          <span>{editorToast}</span>
        </div>
      )}

      {/* Middle Workspace (Left Transcript/Tools + Center Canvas & Reframe Controls) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0 overflow-y-auto lg:overflow-hidden">
        {/* ZONE 1: LEFT PANEL (5 COLS) — Transcript & AI Tools */}
        <div className="lg:col-span-5 flex flex-col border-r border-[var(--border)] bg-[var(--card)] min-h-0">
          {/* Sub-navigation Tabs */}
          <div className="flex border-b border-[var(--border)] px-3 pt-2 gap-1 shrink-0">
            {(
              [
                { id: "transcript", label: "Corte por Texto", icon: Type },
                { id: "captions", label: "Estilo Subtítulos", icon: Captions },
                { id: "broll", label: "AI B-Roll", icon: Film },
                { id: "hook", label: "Rango y Hook", icon: SlidersHorizontal },
              ] as const
            ).map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setLeftTab(tab.id)}
                  className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-semibold transition cursor-pointer ${
                    leftTab === tab.id
                      ? "border-[var(--primary)] text-[var(--primary)]"
                      : "border-transparent text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Left Panel Content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {leftTab === "transcript" && (
              <>
                {/* Smart Cleanup Toolbar */}
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--secondary)]/60 p-3">
                  <div className="text-xs">
                    <div className="font-semibold">
                      Edición de Video Basada en Texto
                    </div>
                    <div className="text-[11px] text-[var(--muted-foreground)]">
                      {deletedWordsCount > 0
                        ? `${deletedWordsCount} palabras recortadas (se saltan al reproducir)`
                        : "Haz clic en una palabra para saltar a ese instante o recortarla"}
                    </div>
                  </div>
                  <button
                    onClick={handleStripAllFillersAndPauses}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-xs font-bold text-black hover:opacity-90 transition cursor-pointer"
                  >
                    <Wand2 className="h-3.5 w-3.5" />
                    <span>Limpiar Muletillas</span>
                  </button>
                </div>

                {/* Word Tokens Grid */}
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/30 p-3.5 flex flex-wrap gap-1.5 max-h-64 overflow-y-auto leading-relaxed">
                  {getCleanVisibleWords(clip.transcriptWords).map((w) => {
                    const isCurrent =
                      playheadSec >= w.start && playheadSec <= w.end + 0.12;
                    const isSelected = w.id === selectedWordId;
                    return (
                      <button
                        key={w.id}
                        onClick={() => handleSelectWord(w)}
                        onDoubleClick={() => handleToggleWordDelete(w.id)}
                        title={`Segundo ${w.start}s (Doble clic para recortar/restaurar)`}
                        style={{ fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif' }}
                        className={`rounded-md px-2 py-1 text-xs transition border cursor-pointer ${
                          w.deleted
                            ? "line-through opacity-35 border-red-500/40 bg-red-500/10 text-red-300"
                            : isCurrent
                            ? "bg-[#bef737] text-black font-black border-[#bef737] shadow-xs"
                            : isSelected
                            ? "border-sky-400 bg-sky-500/20 font-semibold text-sky-200"
                            : w.highlight === "color1"
                            ? "border-[#bef737]/40 bg-[#bef737]/10 text-[#bef737] font-semibold"
                            : w.highlight === "color2"
                            ? "border-[#ffc141]/40 bg-[#ffc141]/10 text-[#ffc141] font-semibold"
                            : "border-transparent hover:bg-[var(--secondary)]"
                        }`}
                      >
                        {w.word}
                        {w.emoji ? ` ${w.emoji}` : ""}
                      </button>
                    );
                  })}
                </div>

                {/* Selected Word Inspector */}
                {selectedWord && (
                  <div className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/50 p-4 space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold">
                        Palabra Seleccionada:{" "}
                        <span className="text-[var(--primary)]">
                          &ldquo;{selectedWord.word}&rdquo;
                        </span>{" "}
                        ({selectedWord.start}s – {selectedWord.end}s)
                      </span>
                      <button
                        onClick={() => seekToRelativeSecond(selectedWord.start, true)}
                        className="text-[11px] font-semibold text-sky-400 hover:underline cursor-pointer"
                      >
                        ▶ Reproducir desde aquí
                      </button>
                    </div>

                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={editingWordText}
                        onChange={(e) => setEditingWordText(e.target.value)}
                        placeholder={selectedWord.word}
                        className="flex-1 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs focus:border-[var(--primary)] focus:outline-none"
                      />
                      <button
                        onClick={handleSaveWordText}
                        className="rounded-xl bg-[var(--primary)] px-3 py-1.5 text-xs font-bold text-black cursor-pointer"
                      >
                        Corregir Texto
                      </button>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => handleCycleWordHighlight(selectedWord.id)}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-semibold hover:border-[var(--primary)] cursor-pointer"
                      >
                        <Highlighter className="h-3.5 w-3.5 text-[#bef737]" />
                        <span>
                          Color Karaoke ({selectedWord.highlight || "none"})
                        </span>
                      </button>

                      <button
                        onClick={() => handleToggleWordDelete(selectedWord.id)}
                        className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold cursor-pointer ${
                          selectedWord.deleted
                            ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                            : "border-red-500/40 bg-red-500/10 text-red-300"
                        }`}
                      >
                        <Scissors className="h-3.5 w-3.5" />
                        <span>
                          {selectedWord.deleted
                            ? "Restaurar en el Video"
                            : "Cortar del Video (Jump-Cut)"}
                        </span>
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}

            {leftTab === "captions" && (
              <div className="space-y-4">
                <div className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                  Plantillas de Subtítulos Karaoke
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {brandTemplates.map((bt) => (
                    <button
                      key={bt.id}
                      onClick={() => updateClipProps({ captionPresetId: bt.id })}
                      className={`rounded-xl border p-3 text-left transition cursor-pointer ${
                        clip.captionPresetId === bt.id
                          ? "border-[var(--primary)] bg-[var(--primary)]/15"
                          : "border-[var(--border)] bg-[var(--secondary)]/50"
                      }`}
                    >
                      <div className="text-xs font-bold">{bt.name}</div>
                      <div className="text-[11px] text-[var(--muted-foreground)]">
                        Animación: {bt.animationStyle}
                      </div>
                      <div className="mt-2 flex items-center gap-1.5">
                        <span
                          className="h-3 w-3 rounded-full border border-white/20"
                          style={{ backgroundColor: bt.highlightColor1 }}
                        />
                        <span
                          className="h-3 w-3 rounded-full border border-white/20"
                          style={{ backgroundColor: bt.highlightColor2 }}
                        />
                        <span className="text-[10px] font-mono text-[var(--muted-foreground)]">
                          {bt.fontFamily} {bt.fontSize}px
                        </span>
                      </div>
                    </button>
                  ))}
                </div>

                {/* Live Caption Properties */}
                <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/40 p-4 space-y-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span>Posición Vertical de Subtítulos</span>
                    <div className="flex gap-1.5">
                      {(["top", "middle", "bottom"] as const).map((pos) => (
                        <button
                          key={pos}
                          onClick={() =>
                            setBrandTemplates((prev) =>
                              prev.map((bt) =>
                                bt.id === activeTemplate.id
                                  ? { ...bt, position: pos }
                                  : bt
                              )
                            )
                          }
                          className={`rounded-lg px-2.5 py-1 capitalize font-semibold cursor-pointer ${
                            activeTemplate.position === pos
                              ? "bg-[var(--primary)] text-black"
                              : "bg-[var(--card)] text-[var(--muted-foreground)]"
                          }`}
                        >
                          {pos}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {leftTab === "broll" && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2.5">
                  <button
                    onClick={() => handleAddBrollSegment("stock")}
                    className="flex items-center justify-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] py-2.5 text-xs font-semibold hover:border-[var(--primary)] transition cursor-pointer text-[var(--foreground)]"
                  >
                    <Plus className="h-4 w-4 text-emerald-500" />
                    <span>Insertar Stock B-Roll</span>
                  </button>
                  <button
                    onClick={() => handleAddBrollSegment("ai_video")}
                    className="flex items-center justify-center gap-1.5 rounded-xl bg-[var(--primary)] py-2.5 text-xs font-bold text-white hover:opacity-95 transition cursor-pointer shadow-xs"
                  >
                    <Sparkles className="h-4 w-4" />
                    <span>Insertar AI Video B-Roll</span>
                  </button>
                </div>

                <div className="space-y-2">
                  {clip.brollSegments.map((seg) => (
                    <div
                      key={seg.id}
                      className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3 text-xs"
                    >
                      <div>
                        <div className="font-semibold">{seg.label}</div>
                        <div className="text-[11px] text-[var(--muted-foreground)]">
                          {seg.startSec}s – {seg.endSec}s · Tipo: {seg.type}
                        </div>
                      </div>
                      <button
                        onClick={() =>
                          updateClipProps({
                            brollSegments: clip.brollSegments.filter(
                              (b) => b.id !== seg.id
                            ),
                          })
                        }
                        className="text-red-400 hover:text-red-300 p-1 cursor-pointer"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {leftTab === "hook" && (
              <div className="space-y-4 text-xs">
                {/* Trim Range Controls */}
                <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3.5 space-y-3">
                  <div className="font-semibold text-[var(--foreground)]">
                    Ajuste Preciso de Corte del Video Original
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] text-[var(--muted-foreground)] mb-1">
                        Segundo Inicial ({formatSecondsToTimecode(clip.startSec)})
                      </label>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => {
                            const nextStart = Math.max(0, clip.startSec - 1);
                            updateClipProps({
                              startSec: nextStart,
                              duration: Math.max(5, clip.endSec - nextStart),
                            });
                          }}
                          className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 font-bold hover:border-[var(--primary)]"
                        >
                          -1s
                        </button>
                        <span className="font-mono font-bold px-2">
                          {clip.startSec}s
                        </span>
                        <button
                          onClick={() => {
                            const nextStart = Math.min(
                              clip.endSec - 5,
                              clip.startSec + 1
                            );
                            updateClipProps({
                              startSec: nextStart,
                              duration: Math.max(5, clip.endSec - nextStart),
                            });
                          }}
                          className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 font-bold hover:border-[var(--primary)]"
                        >
                          +1s
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="block text-[11px] text-[var(--muted-foreground)] mb-1">
                        Segundo Final ({formatSecondsToTimecode(clip.endSec)})
                      </label>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => {
                            const nextEnd = Math.max(
                              clip.startSec + 5,
                              clip.endSec - 1
                            );
                            updateClipProps({
                              endSec: nextEnd,
                              duration: Math.max(5, nextEnd - clip.startSec),
                            });
                          }}
                          className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 font-bold hover:border-[var(--primary)]"
                        >
                          -1s
                        </button>
                        <span className="font-mono font-bold px-2">
                          {clip.endSec}s
                        </span>
                        <button
                          onClick={() => {
                            const nextEnd = clip.endSec + 1;
                            updateClipProps({
                              endSec: nextEnd,
                              duration: Math.max(5, nextEnd - clip.startSec),
                            });
                          }}
                          className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 font-bold hover:border-[var(--primary)]"
                        >
                          +1s
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <label className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
                  <span className="font-semibold">
                    Mostrar Banner Auto-Hook Superior
                  </span>
                  <input
                    type="checkbox"
                    checked={clip.hasAutoHook}
                    onChange={(e) =>
                      updateClipProps({ hasAutoHook: e.target.checked })
                    }
                    className="h-4 w-4 accent-[var(--primary)]"
                  />
                </label>

                <div>
                  <label className="block text-[var(--muted-foreground)] mb-1">
                    Texto del Hook Viral Superior
                  </label>
                  <input
                    type="text"
                    value={clip.hookText}
                    onChange={(e) =>
                      updateClipProps({ hookText: e.target.value })
                    }
                    className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-xs font-bold"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ZONE 2: CENTER CANVAS (7 COLS) — Native Cropped Video Player & Interactive Reframe */}
        <div className="lg:col-span-7 flex flex-col items-center justify-between bg-black/40 p-4 min-h-0">
          <div className="flex flex-wrap items-center justify-between w-full text-xs text-[var(--muted-foreground)] gap-2 mb-1">
            <span>
              Lienzo de Video Real ({clip.aspectRatio} · Layout: {clip.layoutMode} · Encuadre X: {cropX}% · Zoom: {zoom.toFixed(1)}x)
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsMuted((m) => !m)}
                className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-bold bg-[var(--secondary)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer"
              >
                {isMuted ? (
                  <>
                    <VolumeX className="h-3 w-3 text-red-400" />
                    <span>Silenciado</span>
                  </>
                ) : (
                  <>
                    <Volume2 className="h-3 w-3 text-[#bef737]" />
                    <span>Audio Activo</span>
                  </>
                )}
              </button>

              <button
                onClick={() =>
                  setFaceFocusMode(
                    faceFocusMode === "speaker" ? "screen" : "speaker"
                  )
                }
                className={`rounded px-2 py-0.5 text-[11px] font-bold cursor-pointer ${
                  faceFocusMode === "speaker"
                    ? "bg-sky-500/20 text-sky-300 border border-sky-400/50"
                    : "bg-orange-500/20 text-orange-300 border border-orange-500/50"
                }`}
              >
                {faceFocusMode === "speaker"
                  ? "Face Lock (#4af)"
                  : "Action Lock (#e35600)"}
              </button>
            </div>
          </div>

          {/* Video Stage Container (Supports Drag-to-Pan Crop & Click-to-Play) */}
          <div
            onMouseDown={(e) => {
              setIsDraggingCrop(true);
              dragStartXRef.current = e.clientX;
              dragStartCropXRef.current = cropX;
              dragDistanceRef.current = 0;
            }}
            onMouseMove={(e) => {
              if (!isDraggingCrop) return;
              const deltaX = e.clientX - dragStartXRef.current;
              dragDistanceRef.current = Math.abs(deltaX);
              const nextCrop = Math.max(
                0,
                Math.min(100, Math.round(dragStartCropXRef.current - deltaX * 0.35))
              );
              updateClipProps({ cropX: nextCrop });
            }}
            onMouseUp={() => {
              setIsDraggingCrop(false);
              if (dragDistanceRef.current < 5) {
                handleTogglePlay();
              }
            }}
            onMouseLeave={() => setIsDraggingCrop(false)}
            title="Haz clic para reproducir/pausar, o arrastra horizontalmente para encuadrar en 9:16"
            className={`relative overflow-hidden rounded-2xl border border-[var(--border)] bg-black shadow-2xl flex items-center justify-center select-none ${
              isDraggingCrop ? "cursor-grabbing" : "cursor-pointer"
            } ${
              clip.aspectRatio === "9:16"
                ? "aspect-[9/16] h-[460px] sm:h-[500px] lg:h-[540px] max-h-[70vh]"
                : clip.aspectRatio === "1:1"
                ? "aspect-square h-[400px] max-h-[60vh]"
                : clip.aspectRatio === "4:5"
                ? "aspect-[4/5] h-[440px] max-h-[65vh]"
                : "aspect-video w-full max-w-2xl"
            }`}
          >
            {resolvedStreamUrl ? (
              <video
                ref={videoRef}
                src={`${resolvedStreamUrl}#t=${clip.startSec},${clip.endSec}`}
                poster={clip.thumbnailUrl}
                preload="metadata"
                playsInline
                muted={isMuted}
                onLoadedMetadata={(e) => {
                  const v = e.currentTarget;
                  if (v.currentTime < clip.startSec || v.currentTime > clip.endSec) {
                    v.currentTime = clip.startSec;
                  }
                }}
                onTimeUpdate={(e) => {
                  const v = e.currentTarget;
                  if (v.currentTime < clip.startSec - 0.25) {
                    v.currentTime = clip.startSec;
                    return;
                  }
                  if (v.currentTime >= clip.endSec) {
                    v.currentTime = clip.startSec;
                    if (splitVideoRef.current) {
                      splitVideoRef.current.currentTime = clip.startSec;
                    }
                    setPlayheadSec(0);
                    if (!v.paused) v.play().catch(() => {});
                    return;
                  }

                  const relSec = Math.max(
                    0,
                    Number((v.currentTime - clip.startSec).toFixed(2))
                  );

                  // Real Text-Based Jump-Cut: skip over any word marked deleted
                  const deletedHit = clip.transcriptWords.find(
                    (w) =>
                      w.deleted && relSec >= w.start && relSec < w.end - 0.05
                  );
                  if (deletedHit) {
                    const jumpTarget = clip.startSec + deletedHit.end;
                    v.currentTime = jumpTarget;
                    if (splitVideoRef.current) {
                      splitVideoRef.current.currentTime = jumpTarget;
                    }
                    return;
                  }

                  setPlayheadSec(relSec);
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                style={{
                  objectPosition: `${dynamicCropX}% 50%`,
                  transform: `scale(${dynamicZoom})`,
                  transition:
                    "transform 350ms cubic-bezier(0.25, 1, 0.5, 1), object-position 450ms ease",
                }}
                className={`h-full w-full pointer-events-none ${
                  clip.layoutMode === "fit" ? "object-contain" : "object-cover"
                }`}
              />
            ) : (
              <img
                src={clip.thumbnailUrl}
                alt={clip.title}
                style={{
                  objectPosition: `${cropX}% 50%`,
                  transform: `scale(${zoom})`,
                }}
                className={`h-full w-full pointer-events-none ${
                  clip.layoutMode === "fit" ? "object-contain" : "object-cover"
                }`}
              />
            )}

            {/* Split-screen layout (Gameplay top + zoomed Facecam bottom) */}
            {clip.layoutMode === "split" && (
              <div className="absolute inset-x-0 bottom-0 h-1/2 border-t-2 border-[#bef737] overflow-hidden bg-black pointer-events-none">
                {resolvedStreamUrl ? (
                  <video
                    ref={splitVideoRef}
                    src={`${resolvedStreamUrl}#t=${clip.startSec},${clip.endSec}`}
                    muted
                    playsInline
                    style={{
                      objectPosition: `${Math.min(100, Math.max(0, 100 - cropX))}% 35%`,
                      transform: "scale(1.65)",
                    }}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <img
                    src={clip.thumbnailUrl}
                    alt="Split Speaker 2"
                    className="h-full w-full object-cover scale-125"
                  />
                )}
              </div>
            )}

            {/* Active B-Roll Overlay badge */}
            {activeBrollAtPlayhead && (
              <div className="absolute top-12 right-3 rounded-lg bg-purple-600/90 px-2.5 py-1 text-[10px] font-bold text-white shadow-md z-10 pointer-events-none">
                {activeBrollAtPlayhead.label}
              </div>
            )}

            {/* Safe Grid Guidelines */}
            {showSafeGrid && (
              <div className="moveable-CustomGridGuidelines absolute inset-0 pointer-events-none z-10" />
            )}

            {/* Moveable AI Reframe Bounding Box */}
            {showMoveableBox && (
              <div
                className={`moveable-control-box absolute inset-6 pointer-events-none z-10 ${
                  faceFocusMode === "screen" ? "screen-focus" : ""
                }`}
              >
                <div className="moveable-line top-0 left-0 right-0 h-[1.5px]" />
                <div className="moveable-line bottom-0 left-0 right-0 h-[1.5px]" />
                <div className="moveable-line top-0 bottom-0 left-0 w-[1.5px]" />
                <div className="moveable-line top-0 bottom-0 right-0 w-[1.5px]" />
                <div className="moveable-control -top-1.5 -left-1.5" />
                <div className="moveable-control -top-1.5 -right-1.5" />
                <div className="moveable-control -bottom-1.5 -left-1.5" />
                <div className="moveable-control -bottom-1.5 -right-1.5" />
              </div>
            )}

            {/* Auto-Hook Headline Banner */}
            {clip.hasAutoHook && (
              <div
                style={{ fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif' }}
                className="absolute top-3 inset-x-3 rounded-lg bg-[#bef737] px-2.5 py-1 text-center text-[11px] font-black text-black uppercase shadow-md z-10 pointer-events-none"
              >
                {clip.hookText}
              </div>
            )}

            {/* Synchronized Multi-Word Karaoke Caption Overlay (Hides cleanly when silent) */}
            {phraseWords.length > 0 && (
              <div
                className={`absolute inset-x-2.5 text-center pointer-events-none z-20 transition-opacity duration-150 ${
                  activeTemplate.position === "top"
                    ? "top-14"
                    : activeTemplate.position === "middle"
                    ? "top-1/2 -translate-y-1/2"
                    : "bottom-5"
                }`}
              >
                <div className="inline-flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 rounded-xl bg-black/85 backdrop-blur-xs px-3 py-1.5 border border-white/15 shadow-lg">
                  {phraseWords.map((w) => {
                    const isActive =
                      playheadSec >= w.start - 0.05 && playheadSec <= w.end + 0.12;
                    const activeColor =
                      w.highlight === "color2"
                        ? activeTemplate.highlightColor2
                        : activeTemplate.highlightColor1 || "#bef737";
                    return (
                      <span
                        key={w.id}
                        style={{
                          fontFamily: activeTemplate.fontFamily === "Inter" || !activeTemplate.fontFamily
                            ? 'var(--font-josefin), "Josefin Sans", sans-serif'
                            : `${activeTemplate.fontFamily}, var(--font-josefin), "Josefin Sans", sans-serif`,
                          color: isActive ? activeColor : activeTemplate.fontColor || "#ffffff",
                          transform: isActive ? "scale(1.12)" : "scale(1)",
                        }}
                        className="inline-block text-xs sm:text-sm font-black uppercase tracking-wide drop-shadow-[0_2px_4px_rgba(0,0,0,0.95)] transition-all duration-100"
                      >
                        {w.word}
                        {isActive && w.emoji ? ` ${w.emoji}` : ""}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Centered Glassmorphic Play Overlay when paused */}
            {!isPlaying && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleTogglePlay();
                }}
                className="absolute inset-0 m-auto h-16 w-16 rounded-full bg-black/60 backdrop-blur-xs flex items-center justify-center text-white border border-white/20 shadow-2xl hover:scale-110 hover:bg-[var(--primary)] hover:text-black transition cursor-pointer z-30 pointer-events-auto"
                title="Reproducir clip"
              >
                <Play className="h-7 w-7 fill-current ml-0.5" />
              </button>
            )}
          </div>

          {/* Interactive Reframe Pan & Zoom Bar + Transport Controls */}
          <div className="w-full max-w-xl flex flex-col gap-2 pt-2">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--card)]/90 px-3 py-1.5 text-[11px]">
              <div className="flex items-center gap-2 flex-1 min-w-[140px]">
                <Move className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                <span className="text-[var(--muted-foreground)] shrink-0">
                  Encuadre 9:16:
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={cropX}
                  onChange={(e) =>
                    updateClipProps({ cropX: Number(e.target.value) })
                  }
                  className="w-full accent-sky-400 cursor-pointer"
                />
                <span className="font-mono w-8 text-right">{cropX}%</span>
              </div>

              <div className="flex items-center gap-2 min-w-[120px]">
                <ZoomIn className="h-3.5 w-3.5 text-[#bef737] shrink-0" />
                <span className="text-[var(--muted-foreground)] shrink-0">
                  Zoom:
                </span>
                <input
                  type="range"
                  min={1}
                  max={2.2}
                  step={0.05}
                  value={zoom}
                  onChange={(e) =>
                    updateClipProps({ zoom: Number(e.target.value) })
                  }
                  className="w-16 accent-[#bef737] cursor-pointer"
                />
                <span className="font-mono">{zoom.toFixed(1)}x</span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  onClick={() => setAutoZoomEnabled((v) => !v)}
                  className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition cursor-pointer ${
                    autoZoomEnabled
                      ? "bg-[var(--primary)] text-white shadow-xs"
                      : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                  title="Aplica zoom dinámico (punch-in) en ganchos y palabras de impacto"
                >
                  <Sparkles className="h-3 w-3" />
                  <span>Auto-Zoom {autoZoomEnabled ? "ON" : "OFF"}</span>
                </button>

                <button
                  type="button"
                  onClick={() => setAutoReframeEnabled((v) => !v)}
                  className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition cursor-pointer ${
                    autoReframeEnabled
                      ? "bg-emerald-600 text-white shadow-xs"
                      : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                  title="Sigue automáticamente al hablante activo en formato 9:16 vertical"
                >
                  <Scissors className="h-3 w-3" />
                  <span>Auto-Encuadre {autoReframeEnabled ? "ON" : "OFF"}</span>
                </button>
              </div>
            </div>

            <div className="flex items-center justify-center gap-4">
              <button
                onClick={() => seekToRelativeSecond(0, false)}
                className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                title="Ir al inicio del clip"
              >
                <SkipBack className="h-4 w-4" />
              </button>
              <button
                onClick={handleTogglePlay}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--primary)] text-black shadow-md hover:opacity-90 transition cursor-pointer"
              >
                {isPlaying ? (
                  <Pause className="h-4 w-4 fill-current" />
                ) : (
                  <Play className="h-4 w-4 fill-current" />
                )}
              </button>
              <button
                onClick={() => seekToRelativeSecond(maxClipTime - 0.5, false)}
                className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                title="Ir al final del clip"
              >
                <SkipForward className="h-4 w-4" />
              </button>
              <span className="font-mono text-xs text-[var(--muted-foreground)]">
                {formatSecondsToTimecode(clip.startSec + playheadSec)} (
                {playheadSec.toFixed(1)}s / {maxClipTime.toFixed(1)}s)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ZONE 4: BOTTOM 5-TRACK NON-LINEAR TIMELINE */}
      <div className="h-48 border-t border-[var(--border)] bg-[var(--card)] px-4 py-2.5 flex flex-col justify-between shrink-0 select-none">
        {/* Timeline Scrubber Header */}
        <div className="flex items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-3 flex-1">
            <span className="font-semibold text-[var(--muted-foreground)] shrink-0">
              Línea de Tiempo Sincronizada
            </span>
            <input
              type="range"
              min={0}
              max={maxClipTime}
              step={0.1}
              value={playheadSec}
              onChange={(e) => seekToRelativeSecond(Number(e.target.value), false)}
              className="w-full max-w-md accent-[var(--primary)] cursor-pointer"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[var(--muted-foreground)]">
              Zoom Pista
            </span>
            <input
              type="range"
              min={80}
              max={150}
              value={timelineZoom}
              onChange={(e) => setTimelineZoom(Number(e.target.value))}
              className="w-24 accent-[var(--primary)]"
            />
          </div>
        </div>

        {/* 5 Synchronized Tracks */}
        <div className="relative space-y-1.5 overflow-x-auto py-1">
          {/* Playhead Vertical Line */}
          <div
            style={{
              left: `${Math.min(
                98,
                10 + (playheadSec / Math.max(1, maxClipTime)) * 88
              )}%`,
            }}
            className="pointer-events-none absolute inset-y-0 z-20 w-[2px] bg-[#bef737]"
          />

          {/* Track 1: Hook Headline */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="w-24 shrink-0 text-[var(--muted-foreground)] font-medium">
              1. Auto Hook
            </span>
            <div className="flex-1 h-5 rounded bg-[var(--secondary)] relative overflow-hidden">
              {clip.hasAutoHook && (
                <div className="absolute inset-y-0 left-0 w-1/3 rounded bg-amber-500/30 border border-amber-400/50 px-2 flex items-center text-amber-200 truncate">
                  {clip.hookText}
                </div>
              )}
            </div>
          </div>

          {/* Track 2: Karaoke Captions */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="w-24 shrink-0 text-[var(--muted-foreground)] font-medium">
              2. Subtítulos
            </span>
            <div className="flex-1 h-5 rounded bg-[var(--secondary)] flex gap-0.5 overflow-hidden px-1 items-center">
              {getCleanVisibleWords(clip.transcriptWords).slice(0, 22).map((w) => (
                <span
                  key={w.id}
                  onClick={() => handleSelectWord(w)}
                  style={{ fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif' }}
                  className={`cursor-pointer rounded px-1 truncate ${
                    w.deleted
                      ? "bg-red-500/20 text-red-400 line-through"
                      : playheadSec >= w.start && playheadSec <= w.end
                      ? "bg-[#bef737] text-black font-bold"
                      : "bg-[#bef737]/20 text-[#bef737]"
                  }`}
                >
                  {w.word}
                </span>
              ))}
            </div>
          </div>

          {/* Track 3: B-Roll Layer */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="w-24 shrink-0 text-[var(--muted-foreground)] font-medium">
              3. AI B-Roll
            </span>
            <div className="flex-1 h-5 rounded bg-[var(--secondary)] relative overflow-hidden">
              {clip.brollSegments.map((seg) => (
                <div
                  key={seg.id}
                  style={{
                    left: `${(seg.startSec / maxClipTime) * 100}%`,
                    width: `${Math.max(
                      12,
                      ((seg.endSec - seg.startSec) / maxClipTime) * 100
                    )}%`,
                  }}
                  className="absolute inset-y-0 rounded bg-purple-500/35 border border-purple-400/60 px-1.5 flex items-center text-purple-200 truncate"
                >
                  {seg.label}
                </div>
              ))}
            </div>
          </div>

          {/* Track 4: Main Video & AI Reframe Keyframes */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="w-24 shrink-0 text-[var(--muted-foreground)] font-medium">
              4. Video MP4
            </span>
            <div className="flex-1 h-5 rounded bg-sky-500/20 border border-sky-400/40 px-2 flex items-center justify-between text-sky-200">
              <span>
                Flujo MP4 Directo ({clip.aspectRatio} · {clip.layoutMode} · Pan X:{" "}
                {cropX}% · Zoom: {zoom.toFixed(1)}x)
              </span>
              <span>
                {formatSecondsToTimecode(clip.startSec)} –{" "}
                {formatSecondsToTimecode(clip.endSec)}
              </span>
            </div>
          </div>

          {/* Track 5: Audio Waveform */}
          <div className="flex items-center gap-2 text-[10px]">
            <span className="w-24 shrink-0 text-[var(--muted-foreground)] font-medium">
              5. Audio Real
            </span>
            <div className="flex-1 h-5 rounded bg-emerald-500/15 border border-emerald-500/30 px-2 flex items-center gap-1 overflow-hidden">
              {Array.from({ length: 48 }).map((_, idx) => (
                <span
                  key={idx}
                  style={{ height: `${25 + ((idx * 19) % 70)}%` }}
                  className="w-1 bg-emerald-400/70 rounded-full"
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Floating Clip Export Progress Modal / Toast */}
      {isExportingClip && exportProgress && (
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-[var(--border)] bg-[var(--card)]/95 backdrop-blur-md p-4 shadow-2xl flex items-center gap-3.5 min-w-[320px] max-w-[420px] transition-all">
          <div className="h-10 w-10 rounded-xl bg-[var(--primary)]/15 flex items-center justify-center text-[var(--primary)] shrink-0">
            {exportProgress.status === "done" ? (
              <Check className="h-5 w-5 text-emerald-500" />
            ) : (
              <RefreshCw className="h-5 w-5 animate-spin" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-[var(--foreground)] truncate">
              {exportProgress.message}
            </div>
            <div className="w-full bg-[var(--secondary)] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[var(--primary)] h-full transition-all duration-200"
                style={{ width: `${exportProgress.progress}%` }}
              />
            </div>
          </div>
          <span className="text-xs font-extrabold text-[var(--primary)]">
            {exportProgress.progress}%
          </span>
        </div>
      )}
    </div>
  );
}
