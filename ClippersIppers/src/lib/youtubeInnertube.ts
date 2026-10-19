import { TranscriptWord } from "@/types/opus";
import { isNoiseOrPauseWord } from "./transcriptUtils";

export interface RawTimedWord {
  word: string;
  startSec: number;
  endSec: number;
}

export interface InnertubeVideoData {
  videoId: string;
  title: string;
  author: string;
  durationSec: number;
  keywords: string[];
  shortDescription: string;
  directMp4Url?: string;
  highResVideoUrl?: string;
  audioUrl?: string;
  videoQuality?: string;
  streamUserAgent: string;
  words: RawTimedWord[];
  languageCode: string;
}

const IOS_CLIENT = {
  clientName: "IOS",
  clientVersion: "20.03.02",
  deviceMake: "Apple",
  deviceModel: "iPhone16,2",
  osName: "iOS",
  osVersion: "18.2.1.22C161",
  ua: "com.google.ios.youtube/20.03.02 (iPhone16,2; U; CPU iOS 18_2_1 like Mac OS X;)",
};

const ANDROID_CLIENT = {
  clientName: "ANDROID",
  clientVersion: "20.03.32",
  androidSdkVersion: 34,
  osName: "Android",
  osVersion: "14",
  ua: "com.google.android.youtube/20.03.32 (Linux; U; Android 14) gzip",
};

const ANDROID_VR_CLIENT = {
  clientName: "ANDROID_VR",
  clientVersion: "1.60.19",
  ua: "com.google.android.apps.youtube.vr.oculus/1.60.19 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
};

// In-memory cache (persists across requests in the Node process)
const globalForCache = globalThis as unknown as {
  __ytInnertubeCache?: Map<string, { expiresAt: number; data: InnertubeVideoData }>;
};

const ytCache =
  globalForCache.__ytInnertubeCache ||
  (globalForCache.__ytInnertubeCache = new Map());

export function extractYouTubeId(input: string): string | null {
  if (!input) return null;
  const trimmed = input.trim();
  if (/^[a-zA-Z0-9_-]{11}$/.test(trimmed)) return trimmed;
  const match =
    trimmed.match(
      /(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/
    ) || trimmed.match(/\/vi(?:_webp)?\/([a-zA-Z0-9_-]{11})\//);
  return match ? match[1] : null;
}

export async function fetchYouTubeInnertubeData(
  videoIdOrUrl: string
): Promise<InnertubeVideoData | null> {
  const videoId = extractYouTubeId(videoIdOrUrl);
  if (!videoId) return null;

  const cached = ytCache.get(videoId);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data;
  }

  let playerData: any = null;
  let directMp4Url: string | undefined;
  let highResVideoUrl: string | undefined;
  let audioUrl: string | undefined;
  let videoQuality: string | undefined;
  let streamUserAgent = ANDROID_CLIENT.ua;
  let captionTracks: any[] = [];
  let captionUa = IOS_CLIENT.ua;

  // 1. Query ANDROID 20.03.32 first (returns both muxed 360p MP4 stream AND captions)
  try {
    const androidRes = await fetch(
      "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "User-Agent": ANDROID_CLIENT.ua,
        },
        body: JSON.stringify({
          context: {
            client: {
              clientName: ANDROID_CLIENT.clientName,
              clientVersion: ANDROID_CLIENT.clientVersion,
              androidSdkVersion: ANDROID_CLIENT.androidSdkVersion,
              osName: ANDROID_CLIENT.osName,
              osVersion: ANDROID_CLIENT.osVersion,
              hl: "es",
              gl: "US",
            },
          },
          videoId,
        }),
      }
    );

    if (androidRes.ok) {
      const aj = await androidRes.json();
      if (aj?.playabilityStatus?.status === "OK") {
        playerData = aj;
        const muxed = (aj?.streamingData?.formats || []).find(
          (f: any) => f.url && String(f.mimeType || "").includes("video/mp4")
        );
        if (muxed?.url) {
          directMp4Url = muxed.url;
          streamUserAgent = ANDROID_CLIENT.ua;
        }
        const tracks =
          aj?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
        if (Array.isArray(tracks) && tracks.length > 0) {
          captionTracks = tracks;
          captionUa = ANDROID_CLIENT.ua;
        }
      }
    }
  } catch (err) {
    console.warn("ANDROID client fallback:", err);
  }

  // 2. If captions or playerData missing, query IOS 20.03.02
  if (!playerData || captionTracks.length === 0) {
    try {
      const iosRes = await fetch(
        "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "User-Agent": IOS_CLIENT.ua,
          },
          body: JSON.stringify({
            context: {
              client: {
                clientName: IOS_CLIENT.clientName,
                clientVersion: IOS_CLIENT.clientVersion,
                deviceMake: IOS_CLIENT.deviceMake,
                deviceModel: IOS_CLIENT.deviceModel,
                osName: IOS_CLIENT.osName,
                osVersion: IOS_CLIENT.osVersion,
                hl: "es",
                gl: "US",
              },
            },
            videoId,
          }),
        }
      );

      if (iosRes.ok) {
        const ij = await iosRes.json();
        if (ij?.playabilityStatus?.status === "OK") {
          if (!playerData) playerData = ij;
          const tracks =
            ij?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
          if (Array.isArray(tracks) && tracks.length > 0) {
            captionTracks = tracks;
            captionUa = IOS_CLIENT.ua;
          }
          if (!directMp4Url) {
            const muxed = (ij?.streamingData?.formats || []).find(
              (f: any) => f.url && String(f.mimeType || "").includes("video/mp4")
            );
            if (muxed?.url) {
              directMp4Url = muxed.url;
              streamUserAgent = IOS_CLIENT.ua;
            }
          }
        }
      }
    } catch (err) {
      console.warn("IOS client fallback:", err);
    }
  }

  // 3. Fallback to ANDROID_VR if directMp4Url still not found
  if (!directMp4Url) {
    try {
      const vrRes = await fetch(
        "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "User-Agent": ANDROID_VR_CLIENT.ua,
          },
          body: JSON.stringify({
            context: {
              client: {
                clientName: ANDROID_VR_CLIENT.clientName,
                clientVersion: ANDROID_VR_CLIENT.clientVersion,
                hl: "es",
                gl: "US",
              },
              thirdParty: { embedUrl: "https://www.youtube.com/" },
            },
            videoId,
          }),
        }
      );
      if (vrRes.ok) {
        const vj = await vrRes.json();
        if (vj?.playabilityStatus?.status === "OK") {
          if (!playerData) playerData = vj;
          const muxed = (vj?.streamingData?.formats || []).find(
            (f: any) => f.url && String(f.mimeType || "").includes("video/mp4")
          );
          if (muxed?.url) {
            directMp4Url = muxed.url;
            streamUserAgent = ANDROID_VR_CLIENT.ua;
          }
        }
      }
    } catch (err) {
      console.warn("ANDROID_VR client fallback:", err);
    }
  }

  if (!playerData) return null;

  // Extract separate high-definition video (1080p/720p) and pristine audio streams
  if (playerData?.streamingData) {
    const sd = playerData.streamingData;
    const formats = Array.isArray(sd.formats) ? sd.formats : [];
    const adaptive = Array.isArray(sd.adaptiveFormats) ? sd.adaptiveFormats : [];

    // Muxed stream fallback (usually 360p)
    if (!directMp4Url) {
      const muxed =
        formats.find(
          (f: any) => f.url && String(f.mimeType || "").includes("video/mp4")
        ) || formats.find((f: any) => f.url);
      if (muxed?.url) directMp4Url = muxed.url;
    }

    // High resolution video stream: prefer 1080p MP4 (avc1), or highest available MP4/video
    const videoFormats = adaptive.filter(
      (f: any) => f.url && String(f.mimeType || "").startsWith("video/")
    );
    videoFormats.sort(
      (a: any, b: any) => (Number(b.height) || 0) - (Number(a.height) || 0)
    );

    const bestMp4 = videoFormats.find((f: any) =>
      String(f.mimeType || "").includes("video/mp4")
    );
    const chosenVideo = bestMp4 || videoFormats[0];
    if (chosenVideo?.url) {
      highResVideoUrl = chosenVideo.url;
      videoQuality =
        chosenVideo.qualityLabel ||
        (chosenVideo.height ? `${chosenVideo.height}p` : "1080p");
    }

    // Best audio stream: prefer audio/mp4 (AAC itag 140/139)
    const audioFormats = adaptive.filter(
      (f: any) => f.url && String(f.mimeType || "").startsWith("audio/")
    );
    audioFormats.sort(
      (a: any, b: any) => (Number(b.bitrate) || 0) - (Number(a.bitrate) || 0)
    );
    const bestMp4Audio = audioFormats.find((f: any) =>
      String(f.mimeType || "").includes("audio/mp4")
    );
    const chosenAudio = bestMp4Audio || audioFormats[0];
    if (chosenAudio?.url) {
      audioUrl = chosenAudio.url;
    }
  }

  const details = playerData.videoDetails || {};
  const title = details.title || `YouTube Video (${videoId})`;
  const author = details.author || "YouTube Creator";
  const durationSec = Math.max(1, Number(details.lengthSeconds) || 180);
  const keywords: string[] = Array.isArray(details.keywords)
    ? details.keywords.slice(0, 12)
    : [];
  const shortDescription = String(details.shortDescription || "").slice(0, 800);

  // 4. Parse word-level transcript from json3 caption track
  const words: RawTimedWord[] = [];
  let languageCode = "es";

  if (captionTracks.length > 0) {
    const preferredTrack =
      captionTracks.find(
        (t: any) => t.languageCode?.startsWith("es") && t.kind === "asr"
      ) ||
      captionTracks.find((t: any) => t.languageCode?.startsWith("es")) ||
      captionTracks.find((t: any) => t.kind === "asr") ||
      captionTracks.find((t: any) => t.languageCode?.startsWith("en")) ||
      captionTracks[0];

    if (preferredTrack?.baseUrl) {
      languageCode = preferredTrack.languageCode || "es";
      try {
        const cleanBaseUrl = String(preferredTrack.baseUrl).replace(
          /([?&])fmt=[^&]+(&|$)/g,
          "$1"
        );
        const json3Url = `${cleanBaseUrl.replace(/[?&]$/, "")}&fmt=json3`;
        const capRes = await fetch(json3Url, {
          headers: { "User-Agent": captionUa },
        });
        if (capRes.ok) {
          const capJson = await capRes.json();
          for (const ev of capJson.events || []) {
            if (!ev.segs || typeof ev.tStartMs !== "number") continue;
            const baseMs = ev.tStartMs;
            const eventDurMs = ev.dDurationMs || 2200;

            for (let i = 0; i < ev.segs.length; i++) {
              const seg = ev.segs[i];
              const rawText = String(seg.utf8 || "")
                .replace(/\n/g, " ")
                .trim();
              if (!rawText) continue;

              const offsetMs =
                typeof seg.tOffsetMs === "number" ? seg.tOffsetMs : 0;
              const startMs = baseMs + offsetMs;

              let nextStartMs = baseMs + eventDurMs;
              for (let k = i + 1; k < ev.segs.length; k++) {
                if (String(ev.segs[k].utf8 || "").trim()) {
                  nextStartMs =
                    baseMs +
                    (typeof ev.segs[k].tOffsetMs === "number"
                      ? ev.segs[k].tOffsetMs
                      : offsetMs + 320);
                  break;
                }
              }

              const tokens = rawText.split(/\s+/).filter(Boolean);
              const tokenDurMs = Math.max(
                110,
                Math.min(750, (nextStartMs - startMs) / Math.max(1, tokens.length))
              );

              tokens.forEach((tok, idx) => {
                if (isNoiseOrPauseWord(tok)) return;
                const wStart = (startMs + idx * tokenDurMs) / 1000;
                const wEnd = (startMs + (idx + 1) * tokenDurMs) / 1000;
                words.push({
                  word: tok,
                  startSec: Number(wStart.toFixed(2)),
                  endSec: Number(wEnd.toFixed(2)),
                });
              });
            }
          }
        }
      } catch (err) {
        console.warn("Error parsing json3 captions:", err);
      }
    }
  }

  const result: InnertubeVideoData = {
    videoId,
    title,
    author,
    durationSec,
    keywords,
    shortDescription,
    directMp4Url,
    highResVideoUrl,
    audioUrl,
    videoQuality,
    streamUserAgent,
    words,
    languageCode,
  };

  // Cache for 25 minutes
  ytCache.set(videoId, {
    expiresAt: Date.now() + 25 * 60 * 1000,
    data: result,
  });

  return result;
}

/**
 * Formats full video words into timestamped 10-second blocks for LLM prompt context
 */
export function buildTranscriptSummaryForPrompt(
  words: RawTimedWord[],
  maxBlocks = 85
): string {
  if (!words || words.length === 0) return "";
  const blocks: string[] = [];
  let currentBlockStart = words[0].startSec;
  let currentTokens: string[] = [];

  for (const w of words) {
    currentTokens.push(w.word);
    if (w.endSec - currentBlockStart >= 10 || currentTokens.length >= 28) {
      const m = Math.floor(currentBlockStart / 60);
      const s = Math.floor(currentBlockStart % 60);
      const ts = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} (${Math.round(currentBlockStart)}s)`;
      blocks.push(`[${ts}] ${currentTokens.join(" ")}`);
      currentTokens = [];
      currentBlockStart = w.endSec;
    }
  }

  if (currentTokens.length > 0) {
    const m = Math.floor(currentBlockStart / 60);
    const s = Math.floor(currentBlockStart % 60);
    const ts = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} (${Math.round(currentBlockStart)}s)`;
    blocks.push(`[${ts}] ${currentTokens.join(" ")}`);
  }

  if (blocks.length <= maxBlocks) {
    return blocks.join("\n");
  }

  // Sample evenly across the entire video if very long
  const step = blocks.length / maxBlocks;
  const sampled: string[] = [];
  for (let i = 0; i < maxBlocks; i++) {
    sampled.push(blocks[Math.floor(i * step)]);
  }
  return sampled.join("\n");
}

const HIGHLIGHT_COLOR1_WORDS = new Set([
  "brutal",
  "roto",
  "increíble",
  "imposible",
  "secreto",
  "mejor",
  "peor",
  "locura",
  "combo",
  "daño",
  "ganar",
  "perder",
  "nunca",
  "siempre",
  "mira",
  "miren",
  "ojo",
  "cuidado",
  "ataque",
  "golpe",
  "golpes",
  "muerto",
  "mató",
  "viral",
  "millones",
  "dinero",
  "clave",
  "importante",
  "increible",
  "ghostface",
]);

const FILLER_WORDS = new Set([
  "eh",
  "em",
  "um",
  "uh",
  "este",
  "bueno",
  "pues",
  "osea",
]);

const EMOJI_MAP: Record<string, string> = {
  combo: "🔥",
  roto: "💀",
  brutal: "⚡",
  locura: "🤯",
  golpe: "💥",
  golpes: "💥",
  cuchillo: "🔪",
  ghostface: "👻",
  mejor: "🏆",
  ganar: "👑",
  muerto: "☠️",
  like: "👍",
  secreto: "🤫",
  dinero: "💰",
};

/**
 * Extracts the exact real spoken words within [clipStartSec, clipEndSec]
 * and normalizes their timestamps relative to the clip start (0.00s -> clipDuration).
 */
export function sliceRealWordsForClip(
  allWords: RawTimedWord[],
  clipStartSec: number,
  clipEndSec: number,
  clipIndex = 0
): TranscriptWord[] {
  if (!allWords || allWords.length === 0) return [];

  const sliced = allWords.filter(
    (w) => w.endSec > clipStartSec && w.startSec < clipEndSec
  );

  if (sliced.length === 0) return [];

  const result: TranscriptWord[] = [];

  for (let i = 0; i < sliced.length; i++) {
    const w = sliced[i];
    if (isNoiseOrPauseWord(w.word)) continue;

    const relStart = Number(Math.max(0, w.startSec - clipStartSec).toFixed(2));
    const relEnd = Number(
      Math.max(relStart + 0.14, w.endSec - clipStartSec).toFixed(2)
    );

    const clean = w.word
      .replace(/[.,!?;:¡¿"()]/g, "")
      .toLowerCase()
      .trim();

    const isFiller = FILLER_WORDS.has(clean);
    let highlight: "none" | "color1" | "color2" = "none";

    if (HIGHLIGHT_COLOR1_WORDS.has(clean)) {
      highlight = "color1";
    } else if (clean.length >= 7 && i % 5 === 0) {
      highlight = "color2";
    }

    result.push({
      id: `w-${clipIndex}-${i}`,
      word: w.word,
      start: relStart,
      end: relEnd,
      isFiller,
      isPause: false,
      highlight,
      emoji: EMOJI_MAP[clean],
      deleted: false,
    });
  }

  return result;
}
