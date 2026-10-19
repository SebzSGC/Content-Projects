import { NextRequest, NextResponse } from "next/server";
import {
  extractYouTubeId,
  fetchYouTubeInnertubeData,
} from "@/lib/youtubeInnertube";
import fs from "fs";
import path from "path";

const MEDIA_CACHE_DIR = path.join(process.cwd(), ".media-cache");
if (!fs.existsSync(MEDIA_CACHE_DIR)) {
  try {
    fs.mkdirSync(MEDIA_CACHE_DIR, { recursive: true });
  } catch (_) {}
}

function serveLocalFile(
  filePath: string,
  req: NextRequest,
  contentType: string,
  download: boolean,
  filename: string
): NextResponse {
  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const rangeHeader = req.headers.get("range");

  if (rangeHeader) {
    const parts = rangeHeader.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunkSize = end - start + 1;
    const fileStream = fs.createReadStream(filePath, { start, end });

    const headers = new Headers();
    headers.set("Content-Range", `bytes ${start}-${end}/${fileSize}`);
    headers.set("Accept-Ranges", "bytes");
    headers.set("Content-Length", String(chunkSize));
    headers.set("Content-Type", contentType);
    if (download) {
      headers.set("Content-Disposition", `attachment; filename="${filename}"`);
    }

    return new NextResponse(fileStream as any, {
      status: 206,
      headers,
    });
  }

  const fileStream = fs.createReadStream(filePath);
  const headers = new Headers();
  headers.set("Content-Length", String(fileSize));
  headers.set("Content-Type", contentType);
  headers.set("Accept-Ranges", "bytes");
  if (download) {
    headers.set("Content-Disposition", `attachment; filename="${filename}"`);
  }

  return new NextResponse(fileStream as any, {
    status: 200,
    headers,
  });
}

export async function GET(req: NextRequest) {
  try {
    const rawId =
      req.nextUrl.searchParams.get("videoId") ||
      req.nextUrl.searchParams.get("url") ||
      "";
    const download = req.nextUrl.searchParams.get("download") === "1";
    const videoId = extractYouTubeId(rawId);

    if (!videoId) {
      return NextResponse.json(
        { error: "Se requiere un videoId válido de YouTube." },
        { status: 400 }
      );
    }

    const localCachedPath = path.join(MEDIA_CACHE_DIR, `${videoId}.mp4`);
    const safeTitle = `${videoId}.mp4`;

    // 1. Serve directly from local disk cache if already saved (0ms seek latency)
    if (fs.existsSync(localCachedPath) && fs.statSync(localCachedPath).size > 100000) {
      return serveLocalFile(localCachedPath, req, "video/mp4", download, safeTitle);
    }

    // 2. Fetch remote Innertube metadata
    const ytData = await fetchYouTubeInnertubeData(videoId);
    if (!ytData) {
      return NextResponse.json(
        { error: "No se pudieron obtener los datos de YouTube para este video." },
        { status: 404 }
      );
    }

    const streamType = req.nextUrl.searchParams.get("type"); // "video" | "audio" | "muxed"
    let targetUrl = ytData.directMp4Url;
    if (streamType === "video" && ytData.highResVideoUrl) {
      targetUrl = ytData.highResVideoUrl;
    } else if (streamType === "audio" && ytData.audioUrl) {
      targetUrl = ytData.audioUrl;
    }

    if (!targetUrl) {
      return NextResponse.json(
        { error: `No se encontró flujo disponible para tipo: ${streamType || "muxed"}.` },
        { status: 404 }
      );
    }

    const rangeHeader = req.headers.get("range");
    const fetchHeaders: Record<string, string> = {
      "User-Agent": ytData.streamUserAgent,
      Accept: "*/*",
    };
    if (rangeHeader) {
      fetchHeaders["Range"] = rangeHeader;
    }

    let upstreamRes = await fetch(targetUrl, {
      headers: fetchHeaders,
    });

    // Transparent fallback to directMp4Url if adaptive stream is rejected with 403
    if (upstreamRes.status === 403 && ytData.directMp4Url && targetUrl !== ytData.directMp4Url) {
      targetUrl = ytData.directMp4Url;
      upstreamRes = await fetch(targetUrl, {
        headers: fetchHeaders,
      });
    }

    if (!upstreamRes.ok && upstreamRes.status !== 206) {
      return NextResponse.json(
        { error: `Error upstream ${upstreamRes.status} al transmitir video.` },
        { status: upstreamRes.status }
      );
    }

    const responseHeaders = new Headers();
    responseHeaders.set(
      "Content-Type",
      upstreamRes.headers.get("content-type") || "video/mp4"
    );
    responseHeaders.set("Accept-Ranges", "bytes");

    const contentLength = upstreamRes.headers.get("content-length");
    if (contentLength) {
      responseHeaders.set("Content-Length", contentLength);
    }

    const contentRange = upstreamRes.headers.get("content-range");
    if (contentRange) {
      responseHeaders.set("Content-Range", contentRange);
    }

    if (download) {
      const downloadTitle = ytData.title
        .replace(/[^a-zA-Z0-9_\-\s]/g, "")
        .trim()
        .slice(0, 48) || videoId;
      responseHeaders.set(
        "Content-Disposition",
        `attachment; filename="${downloadTitle}.mp4"`
      );
    }

    // Background cache download: if this is a full request without range, save to local disk cache
    if (!rangeHeader && targetUrl === ytData.directMp4Url && !fs.existsSync(localCachedPath)) {
      (async () => {
        try {
          const bgRes = await fetch(targetUrl, {
            headers: { "User-Agent": ytData.streamUserAgent },
          });
          if (bgRes.ok) {
            const buf = Buffer.from(await bgRes.arrayBuffer());
            if (buf.length > 50000) {
              fs.writeFileSync(localCachedPath, buf);
            }
          }
        } catch (_) {}
      })();
    }

    return new NextResponse(upstreamRes.body, {
      status: upstreamRes.status,
      headers: responseHeaders,
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || "Error interno en proxy de video." },
      { status: 500 }
    );
  }
}
