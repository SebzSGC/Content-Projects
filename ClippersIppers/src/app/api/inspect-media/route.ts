import { NextRequest, NextResponse } from "next/server";
import { VideoSourcePlatform } from "@/types/opus";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const targetUrl = searchParams.get("url")?.trim();

  if (!targetUrl) {
    return NextResponse.json(
      { valid: false, errorMessage: "Parámetro 'url' requerido." },
      { status: 400 }
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(targetUrl);
  } catch {
    return NextResponse.json(
      { valid: false, errorMessage: "URL no válida." },
      { status: 400 }
    );
  }

  const host = parsed.hostname.toLowerCase();

  // 1. YOUTUBE (Videos, Shorts, Live, Embed)
  if (host.includes("youtube.com") || host.includes("youtu.be")) {
    let videoId = "";
    if (host.includes("youtu.be")) {
      videoId = parsed.pathname.slice(1).split("/")[0] || "";
    } else if (parsed.pathname.includes("/shorts/")) {
      videoId = parsed.pathname.split("/shorts/")[1]?.split("/")[0] || "";
    } else if (parsed.pathname.includes("/embed/")) {
      videoId = parsed.pathname.split("/embed/")[1]?.split("/")[0] || "";
    } else if (parsed.pathname.includes("/live/")) {
      videoId = parsed.pathname.split("/live/")[1]?.split("/")[0] || "";
    } else {
      videoId = parsed.searchParams.get("v") || "";
    }

    if (!videoId) {
      return NextResponse.json(
        { valid: false, errorMessage: "No se pudo extraer el ID del video de YouTube." },
        { status: 400 }
      );
    }

    let title = `YouTube Video (${videoId})`;
    let author = "YouTube Creator";
    let thumbnailUrl = `https://i.ytimg.com/vi/${videoId}/maxresdefault.jpg`;
    let durationSec = 720; // 12 min fallback
    let keywords: string[] = ["YouTube", "Viral", "Shorts"];

    // Fetch official public oEmbed
    try {
      const oembedRes = await fetch(
        `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`,
        { next: { revalidate: 3600 } }
      );
      if (oembedRes.ok) {
        const oembed = await oembedRes.json();
        if (oembed.title) title = oembed.title;
        if (oembed.author_name) author = oembed.author_name;
        if (oembed.thumbnail_url) thumbnailUrl = oembed.thumbnail_url;
      }
    } catch (e) {
      console.warn("oEmbed fetch failed:", e);
    }

    // Fetch exact approxDurationMs & keywords from watch page
    try {
      const pageRes = await fetch(`https://www.youtube.com/watch?v=${videoId}`, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
          "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        },
        next: { revalidate: 3600 },
      });
      if (pageRes.ok) {
        const html = await pageRes.text();
        const durMatch = html.match(/"approxDurationMs":"(\d+)"/);
        if (durMatch && durMatch[1]) {
          const parsedSec = Math.round(Number(durMatch[1]) / 1000);
          if (parsedSec > 0) durationSec = parsedSec;
        }

        const kwMatch = html.match(/"keywords":(\[.*?\])/);
        if (kwMatch && kwMatch[1]) {
          try {
            const parsedKw = JSON.parse(kwMatch[1]);
            if (Array.isArray(parsedKw) && parsedKw.length > 0) {
              keywords = parsedKw.slice(0, 8);
            }
          } catch {}
        }
      }
    } catch (e) {
      console.warn("HTML page duration scrape failed:", e);
    }

    return NextResponse.json({
      valid: true,
      platform: "YOUTUBE" as VideoSourcePlatform,
      videoId,
      title,
      author,
      durationSec,
      estimatedDurationSec: durationSec,
      resolution: durationSec > 1800 ? "1080p" : "1080p",
      thumbnailUrl,
      embedUrl: `https://www.youtube.com/embed/${videoId}?autoplay=0`,
      keywords,
    });
  }

  // 2. VIMEO
  if (host.includes("vimeo.com")) {
    try {
      const vimeoRes = await fetch(
        `https://vimeo.com/api/oembed.json?url=${encodeURIComponent(targetUrl)}`
      );
      if (vimeoRes.ok) {
        const vdata = await vimeoRes.json();
        return NextResponse.json({
          valid: true,
          platform: "LOCAL" as VideoSourcePlatform,
          title: vdata.title || "Vimeo Video",
          author: vdata.author_name || "Vimeo Creator",
          durationSec: vdata.duration || 600,
          estimatedDurationSec: vdata.duration || 600,
          resolution: "1080p",
          thumbnailUrl: vdata.thumbnail_url,
          embedUrl: vdata.html,
          keywords: ["Vimeo", "HD"],
        });
      }
    } catch {}
  }

  // 3. LOOM
  if (host.includes("loom.com")) {
    return NextResponse.json({
      valid: true,
      platform: "LOOM" as VideoSourcePlatform,
      title: "Loom Screen & Cam Recording",
      author: "Loom User",
      durationSec: 480,
      estimatedDurationSec: 480,
      resolution: "1080p",
      thumbnailUrl: "https://i.ytimg.com/vi_webp/9qfwPv7clEw/maxresdefault.webp",
      embedUrl: targetUrl.replace("/share/", "/embed/"),
      keywords: ["Loom", "SaaS", "Screen Recording"],
    });
  }

  // 4. RUMBLE / TWITCH / KICK
  return NextResponse.json({
    valid: true,
    platform: (host.includes("rumble.com")
      ? "RUMBLE"
      : host.includes("twitch.tv")
      ? "TWITCH"
      : host.includes("kick.com")
      ? "KICK"
      : "YOUTUBE") as VideoSourcePlatform,
    title: `Online Stream Video (${parsed.pathname.split("/").filter(Boolean).pop() || "Live"})`,
    author: "Streamer",
    durationSec: 1500,
    estimatedDurationSec: 1500,
    resolution: "1080p",
    thumbnailUrl: "https://i.ytimg.com/vi_webp/I33o9UnUe1A/maxresdefault.webp",
    keywords: ["Stream", "Highlights"],
  });
}
