import { TranscriptWord } from "@/types/opus";
import { getCleanVisibleWords, getNaturalSubtitlePhrase } from "./transcriptUtils";
import { extractYouTubeId } from "./youtubeInnertube";

export interface ClipExportProgress {
  status: "preparing" | "rendering" | "encoding" | "done" | "error";
  progress: number;
  message: string;
}

export interface ExportClipOptions {
  videoUrl: string;
  videoId?: string;
  startSec: number;
  endSec: number;
  title: string;
  transcriptWords: TranscriptWord[];
  aspectRatio?: string;
  cropX?: number;
  zoom?: number;
  hookText?: string;
  burnSubtitles?: boolean;
  onProgress?: (p: ClipExportProgress) => void;
}

/**
 * Downloads the exact clipped segment in 1080p Full HD with burned-in karaoke subtitles,
 * 100% pristine AAC audio and 9:16 vertical framing.
 */
export async function exportAndDownloadClip({
  videoUrl,
  videoId,
  startSec,
  endSec,
  title,
  transcriptWords,
  aspectRatio = "9:16",
  cropX = 50,
  zoom = 1.0,
  hookText,
  burnSubtitles = true,
  onProgress,
}: ExportClipOptions): Promise<void> {
  const safeTitle =
    title.replace(/[^a-zA-Z0-9_\-\s]/g, "").trim().slice(0, 42) || "clip";

  const resolvedVideoId =
    videoId ||
    extractYouTubeId(videoUrl) ||
    (videoUrl.includes("videoId=")
      ? videoUrl.split("videoId=")[1]?.split("&")[0]
      : undefined);

  onProgress?.({
    status: "preparing",
    progress: 15,
    message: "Iniciando motor Full HD con subtítulos quemados y audio AAC...",
  });

  if (!resolvedVideoId) {
    onProgress?.({
      status: "error",
      progress: 0,
      message: "No se encontró el identificador del video para exportar.",
    });
    throw new Error("No se pudo identificar el video para la exportación.");
  }

  // 1. Primary: Server-side FFmpeg Full HD pipeline with burned-in karaoke subtitles
  onProgress?.({
    status: "rendering",
    progress: 30,
    message: "Renderizando clip 1080p con subtítulos dinámicos sincronizados...",
  });

  let currentProgress = 30;
  const progressTimer = setInterval(() => {
    currentProgress = Math.min(92, currentProgress + 8);
    onProgress?.({
      status: "rendering",
      progress: currentProgress,
      message: "Compilando video Full HD 1080x1920 y subtítulos incrustados...",
    });
  }, 600);

  const postPayload = {
    videoId: resolvedVideoId,
    startSec,
    endSec,
    aspectRatio,
    cropX,
    title: safeTitle,
    words: transcriptWords,
    hookText,
    burnSubtitles,
  };

  try {
    const res = await fetch("/api/export-clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(postPayload),
    });
    clearInterval(progressTimer);

    if (res.ok && res.headers.get("content-type")?.includes("video")) {
      onProgress?.({
        status: "done",
        progress: 100,
        message: "¡Clip Full HD descargado exitosamente!",
      });
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${safeTitle}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
      return;
    }

    const errJson = await res.json().catch(() => null);
    console.warn("POST export failed, trying GET fallback...", errJson?.error);
  } catch (err) {
    clearInterval(progressTimer);
    console.warn("Error en exportador FFmpeg POST, probando GET fallback...", err);
  }

  // Secondary: Server-side GET fallback
  try {
    const serverGetUrl = `/api/export-clip?videoId=${encodeURIComponent(
      resolvedVideoId
    )}&startSec=${startSec}&endSec=${endSec}&aspectRatio=${encodeURIComponent(
      aspectRatio
    )}&cropX=${cropX}&title=${encodeURIComponent(safeTitle)}&hookText=${encodeURIComponent(
      hookText || ""
    )}&subtitles=${burnSubtitles ? "1" : "0"}`;

    const resGet = await fetch(serverGetUrl);
    if (resGet.ok && resGet.headers.get("content-type")?.includes("video")) {
      onProgress?.({
        status: "done",
        progress: 100,
        message: "¡Clip Full HD descargado exitosamente!",
      });
      const blob = await resGet.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${safeTitle}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
      return;
    }

    const errText = await resGet.text().catch(() => "");
    throw new Error(`Error en servidor de exportación: ${errText || resGet.statusText}`);
  } catch (errGet: any) {
    onProgress?.({
      status: "error",
      progress: 0,
      message: `Error al exportar: ${errGet?.message || "Desconocido"}`,
    });
    throw errGet;
  }
}
