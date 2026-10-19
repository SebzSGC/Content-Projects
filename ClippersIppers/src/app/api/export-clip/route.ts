import { NextRequest, NextResponse } from "next/server";
import {
  extractYouTubeId,
  fetchYouTubeInnertubeData,
  sliceRealWordsForClip,
} from "@/lib/youtubeInnertube";
import { getCleanVisibleWords, getNaturalSubtitlePhrase } from "@/lib/transcriptUtils";
import { TranscriptWord } from "@/types/opus";
import ffmpegStaticPath from "ffmpeg-static";
import { exec } from "child_process";
import fs from "fs";
import path from "path";
import os from "os";

function getFfmpegBinary(): string | null {
  // 1. Direct project node_modules location
  const projectNodeModulesPath = path.join(
    process.cwd(),
    "node_modules",
    "ffmpeg-static",
    process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg"
  );
  if (fs.existsSync(projectNodeModulesPath)) {
    return projectNodeModulesPath;
  }

  // 2. Fallback to imported package path
  const rawPath =
    typeof ffmpegStaticPath === "string"
      ? ffmpegStaticPath
      : (ffmpegStaticPath as any)?.default;
  if (rawPath && fs.existsSync(rawPath)) {
    return rawPath;
  }

  return null;
}

function formatAssTime(sec: number): string {
  const sClamped = Math.max(0, sec);
  const h = Math.floor(sClamped / 3600);
  const m = Math.floor((sClamped % 3600) / 60);
  const s = Math.floor(sClamped % 60);
  const cs = Math.floor((sClamped % 1) * 100);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

/**
 * Builds an Advanced SubStation Alpha (.ass) file with:
 * - Josefin Sans / Arial font with black outline and drop shadow
 * - Gold / Yellow active word highlight (&H0024BFFB&)
 * - Natural phrases (max 4 words)
 * - Complete subtitle silence when speaker is not talking
 * - Optional top viral hook banner for the first 3.2 seconds
 */
function buildAssSubtitleContent(
  rawWords: TranscriptWord[],
  clipStartSec: number,
  clipEndSec: number,
  hookText?: string
): string {
  const visible = getCleanVisibleWords(rawWords);

  const header = `[Script Info]
Title: High Definition Clip Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Josefin Sans,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,4.0,2.0,2,50,50,280,1
Style: Hook,Josefin Sans,44,&H00FFFFFF,&H000000FF,&H00000000,&H00D3456F,-1,0,0,0,100,100,1,0,1,3.5,1.5,8,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`;

  const events: string[] = [];

  // Top Hook banner for first 3.2s
  if (hookText && hookText.trim()) {
    const safeHook = hookText.trim().toUpperCase().replace(/[{}]/g, "");
    events.push(
      `Dialogue: 1,0:00:00.00,0:00:03.20,Hook,,0,0,0,,${safeHook}`
    );
  }

  // Active karaoke words
  if (visible.length > 0) {
    const offset = visible[0].start > clipStartSec ? clipStartSec : 0;

    for (let i = 0; i < visible.length; i++) {
      const w = visible[i];
      const relStart = Math.max(0, w.start - offset);
      const nextWord = visible[i + 1];
      let relEnd = Math.max(relStart + 0.15, w.end - offset);

      // Smooth highlight continuation if next word starts soon (<0.25s)
      if (nextWord) {
        const nextRelStart = Math.max(0, nextWord.start - offset);
        const gap = nextRelStart - relEnd;
        if (gap > 0 && gap < 0.25) {
          relEnd = nextRelStart;
        }
      }

      const phrase = getNaturalSubtitlePhrase(visible, i, relStart + 0.05);
      const targetPhrase = phrase.length > 0 ? phrase : [w];

      const lineText = targetPhrase
        .map((pw) => {
          const cleanWord = pw.word.toUpperCase().replace(/[{}]/g, "");
          if (pw.id === w.id) {
            // Gold / Yellow active word: &H0024BFFB&
            return `{\\c&H0024BFFB&\\b1}${cleanWord}{\\c&H00FFFFFF&\\b0}`;
          }
          return cleanWord;
        })
        .join(" ");

      events.push(
        `Dialogue: 0,${formatAssTime(relStart)},${formatAssTime(relEnd)},Default,,0,0,0,,${lineText}`
      );
    }
  }

  return header + events.join("\n") + "\n";
}

interface ExportClipParams {
  videoId: string;
  startSec: number;
  endSec: number;
  title: string;
  aspectRatio: string;
  cropX: number;
  words?: TranscriptWord[];
  hookText?: string;
  burnSubtitles?: boolean;
}

async function handleClipExport({
  videoId,
  startSec,
  endSec,
  title,
  aspectRatio,
  cropX,
  words,
  hookText,
  burnSubtitles = true,
}: ExportClipParams) {
  const ffmpeg = getFfmpegBinary();
  if (!ffmpeg) {
    return NextResponse.json({
      success: false,
      ffmpegAvailable: false,
      error: "FFmpeg no está disponible en el servidor.",
    });
  }

  const ytData = await fetchYouTubeInnertubeData(videoId);
  if (!ytData?.directMp4Url && !ytData?.highResVideoUrl) {
    return NextResponse.json(
      { success: false, error: "No se pudo obtener el flujo de video de YouTube." },
      { status: 404 }
    );
  }

  const safeTitle =
    title.replace(/[^a-zA-Z0-9_\-\s]/g, "").trim().slice(0, 48) || `clip-${videoId}`;
  const tmpDir = os.tmpdir();
  const timestamp = Date.now();
  const outPath = path.join(tmpDir, `clip_${timestamp}_${safeTitle}.mp4`);
  let assPath: string | null = null;

  // Resolve transcript words
  let resolvedWords: TranscriptWord[] = [];
  if (Array.isArray(words) && words.length > 0) {
    resolvedWords = words;
  } else if (ytData.words && ytData.words.length > 0) {
    resolvedWords = sliceRealWordsForClip(ytData.words, startSec, endSec, 0);
  }

  // Create ASS subtitle file if burning is enabled and words or hook exist
  if (burnSubtitles && (resolvedWords.length > 0 || (hookText && hookText.trim()))) {
    try {
      assPath = path.join(tmpDir, `subs_${timestamp}_${Math.random().toString(36).slice(2)}.ass`);
      const assContent = buildAssSubtitleContent(
        resolvedWords,
        startSec,
        endSec,
        hookText
      );
      fs.writeFileSync(assPath, assContent, "utf-8");
    } catch (e) {
      console.warn("No se pudo escribir archivo ASS temporal:", e);
      assPath = null;
    }
  }

  const port = process.env.PORT || 3040;
  const localBase = `http://127.0.0.1:${port}`;

  // Check if video is already downloaded in local disk cache (.media-cache) for 0ms latency offline rendering
  const localCachedFile = path.join(process.cwd(), ".media-cache", `${videoId}.mp4`);
  const isLocallyCached = fs.existsSync(localCachedFile) && fs.statSync(localCachedFile).size > 1024 * 100;

  // Route stream inputs through local cached file or localhost video-stream proxy to bypass Google CDN 403 Forbidden
  let videoInput = `${localBase}/api/video-stream?videoId=${videoId}`;
  let audioInput = `${localBase}/api/video-stream?videoId=${videoId}`;
  let isDualInput = false;

  if (isLocallyCached) {
    videoInput = localCachedFile;
    audioInput = localCachedFile;
    isDualInput = false;
  } else if (ytData.highResVideoUrl && ytData.audioUrl) {
    videoInput = `${localBase}/api/video-stream?videoId=${videoId}&type=video`;
    audioInput = `${localBase}/api/video-stream?videoId=${videoId}&type=audio`;
    isDualInput = true;
  }

  // Build video filter
  const cropFactor = Math.max(0, Math.min(100, cropX)) / 100;
  let vfParts: string[] = [];

  if (aspectRatio === "9:16") {
    // Exact 9:16 crop followed by Lanczos upscale to Full HD 1080x1920
    vfParts.push(
      `crop=w='2*floor(ih*9/32)':h='2*floor(ih/2)':x='(iw-2*floor(ih*9/32))*${cropFactor}':y=0`
    );
    vfParts.push("scale=1080:1920:flags=lanczos");
  } else if (aspectRatio === "1:1") {
    vfParts.push(
      `crop=w='min(iw,ih)':h='min(iw,ih)':x='(iw-min(iw,ih))*${cropFactor}':y=0`
    );
    vfParts.push("scale=1080:1080:flags=lanczos");
  } else {
    // 16:9 or horizontal: ensure 1080p scale
    vfParts.push("scale=1920:1080:flags=lanczos:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2");
  }

  // Append burned subtitles if ASS file was created
  if (assPath && fs.existsSync(assPath)) {
    // In Windows, escape backslashes and colons for the FFmpeg ass filter
    const escapedAss = assPath.replace(/\\/g, "/").replace(/:/g, "\\:");
    vfParts.push(`ass='${escapedAss}'`);
  }

  const vfFilter = vfParts.join(",");

  // Construct FFmpeg command arguments
  const duration = Math.max(3, endSec - startSec);
  let cmd = "";

  if (isDualInput) {
    cmd = `"${ffmpeg}" -y -ss ${startSec} -t ${duration} -i "${videoInput}" -ss ${startSec} -t ${duration} -i "${audioInput}" -vf "${vfFilter}" -c:v libx264 -preset veryfast -crf 18 -b:v 5000k -maxrate 6500k -bufsize 8000k -pix_fmt yuv420p -c:a aac -b:a 192k -ar 44100 -movflags +faststart "${outPath}"`;
  } else {
    cmd = `"${ffmpeg}" -y -ss ${startSec} -t ${duration} -i "${videoInput}" -vf "${vfFilter}" -c:v libx264 -preset veryfast -crf 18 -b:v 5000k -maxrate 6500k -bufsize 8000k -pix_fmt yuv420p -c:a aac -b:a 192k -ar 44100 -movflags +faststart "${outPath}"`;
  }

  return new Promise<NextResponse>((resolve) => {
    exec(cmd, { timeout: 60000 }, (err) => {
      if (!err && fs.existsSync(outPath)) {
        if (assPath && fs.existsSync(assPath)) {
          try { fs.unlinkSync(assPath); } catch (_) {}
        }
        resolve(serveFileStream(outPath, safeTitle));
        return;
      }

      console.warn("Fallo transcodificación dual 1080p, intentando fallback con proxy unificado y subtítulos:", err?.message);
      
      // Fallback 1: Local disk cache or local proxy muxed stream WITH the exact same burned ASS subtitles & 1080x1920 Lanczos upscale
      const fallbackProxy = isLocallyCached ? localCachedFile : `${localBase}/api/video-stream?videoId=${videoId}`;
      const fallbackCmd1 = `"${ffmpeg}" -y -ss ${startSec} -t ${duration} -i "${fallbackProxy}" -vf "${vfFilter}" -c:v libx264 -preset veryfast -crf 19 -c:a aac -b:a 192k -ar 44100 -movflags +faststart "${outPath}"`;

      exec(fallbackCmd1, { timeout: 45000 }, (fbErr1) => {
        if (!fbErr1 && fs.existsSync(outPath)) {
          if (assPath && fs.existsSync(assPath)) {
            try { fs.unlinkSync(assPath); } catch (_) {}
          }
          resolve(serveFileStream(outPath, safeTitle));
          return;
        }

        console.warn("Fallo fallback 1, intentando fallback directo con subtítulos:", fbErr1?.message);

        // Fallback 2: Direct muxed stream from YouTube CDN with subtitles
        const cdnUrl = ytData.directMp4Url || fallbackProxy;
        const fallbackCmd2 = `"${ffmpeg}" -y -ss ${startSec} -t ${duration} -i "${cdnUrl}" -vf "${vfFilter}" -c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 192k -ar 44100 -movflags +faststart "${outPath}"`;

        exec(fallbackCmd2, { timeout: 35000 }, (fbErr2) => {
          // Clean up ASS file before final non-subtitled fallbacks
          if (assPath && fs.existsSync(assPath)) {
            try { fs.unlinkSync(assPath); } catch (_) {}
          }

          if (!fbErr2 && fs.existsSync(outPath)) {
            resolve(serveFileStream(outPath, safeTitle));
            return;
          }

          console.warn("Fallo fallback 2, intentando transcode sin subtítulos:", fbErr2?.message);

          // Fallback 3: Transcode without subtitles
          const noSubVf = `crop=w='2*floor(ih*9/32)':h='2*floor(ih/2)':x='(iw-2*floor(ih*9/32))*${cropFactor}':y=0,scale=1080:1920:flags=lanczos`;
          const fallbackCmd3 = `"${ffmpeg}" -y -ss ${startSec} -t ${duration} -i "${cdnUrl}" -vf "${noSubVf}" -c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 192k -ar 44100 -movflags +faststart "${outPath}"`;

          exec(fallbackCmd3, { timeout: 25000 }, (fbErr3) => {
            if (!fbErr3 && fs.existsSync(outPath)) {
              resolve(serveFileStream(outPath, safeTitle));
              return;
            }

            resolve(
              NextResponse.json(
                { success: false, error: "No se pudo generar el clip de video tras múltiples intentos." },
                { status: 500 }
              )
            );
          });
        });
      });
    });
  });
}

function serveFileStream(outPath: string, safeTitle: string): NextResponse {
  const stat = fs.statSync(outPath);
  const fileStream = fs.createReadStream(outPath);

  const headers = new Headers();
  headers.set("Content-Type", "video/mp4");
  headers.set("Content-Length", String(stat.size));
  headers.set(
    "Content-Disposition",
    `attachment; filename="${safeTitle}.mp4"`
  );

  // Clean up temporary output video after 60 seconds
  setTimeout(() => {
    try {
      if (fs.existsSync(outPath)) fs.unlinkSync(outPath);
    } catch (_) {}
  }, 60000);

  return new NextResponse(fileStream as any, {
    status: 200,
    headers,
  });
}

export async function HEAD(req: NextRequest) {
  const ffmpeg = getFfmpegBinary();
  if (!ffmpeg) {
    return new NextResponse(null, { status: 503 });
  }
  return new NextResponse(null, {
    status: 200,
    headers: { "Content-Type": "video/mp4" },
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const videoId = extractYouTubeId(body.videoId || "");
    const startSec = Math.max(0, Number(body.startSec) || 0);
    const endSec = Math.max(startSec + 3, Number(body.endSec) || startSec + 45);
    const title = String(body.title || "clip");
    const aspectRatio = String(body.aspectRatio || "9:16");
    const cropX = Math.max(0, Math.min(100, Number(body.cropX) ?? 50));
    const words = Array.isArray(body.words) ? body.words : undefined;
    const hookText = body.hookText ? String(body.hookText) : undefined;
    const burnSubtitles = body.burnSubtitles !== false;

    if (!videoId) {
      return NextResponse.json(
        { success: false, error: "videoId requerido." },
        { status: 400 }
      );
    }

    return await handleClipExport({
      videoId,
      startSec,
      endSec,
      title,
      aspectRatio,
      cropX,
      words,
      hookText,
      burnSubtitles,
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err?.message || "Error procesando el clip." },
      { status: 500 }
    );
  }
}

export async function GET(req: NextRequest) {
  try {
    const videoId = extractYouTubeId(req.nextUrl.searchParams.get("videoId") || "");
    const startSec = Math.max(0, Number(req.nextUrl.searchParams.get("startSec")) || 0);
    const endSec = Math.max(startSec + 3, Number(req.nextUrl.searchParams.get("endSec")) || startSec + 45);
    const title = req.nextUrl.searchParams.get("title") || "clip";
    const aspectRatio = req.nextUrl.searchParams.get("aspectRatio") || "9:16";
    const cropX = Math.max(0, Math.min(100, Number(req.nextUrl.searchParams.get("cropX")) || 50));
    const hookText = req.nextUrl.searchParams.get("hookText") || undefined;
    const burnSubtitles = req.nextUrl.searchParams.get("subtitles") !== "0";

    if (!videoId) {
      return NextResponse.json(
        { success: false, error: "videoId requerido." },
        { status: 400 }
      );
    }

    return await handleClipExport({
      videoId,
      startSec,
      endSec,
      title,
      aspectRatio,
      cropX,
      hookText,
      burnSubtitles,
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err?.message || "Error procesando el clip." },
      { status: 500 }
    );
  }
}
