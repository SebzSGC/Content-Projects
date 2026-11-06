import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SERVER_BASE = (process.env.CLIPS_SERVER_URL || "http://127.0.0.1:8790").replace(/\/+$/, "");

async function proxyRequest(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const subPath = (path || []).join("/");
  const search = req.nextUrl.search || "";
  const targetUrl = `${SERVER_BASE}/${subPath}${search}`;

  const headers = new Headers();
  for (const key of ["accept", "content-type", "range", "if-range"]) {
    const val = req.headers.get(key);
    if (val) headers.set(key, val);
  }

  const isBodyMethod = req.method !== "GET" && req.method !== "HEAD";
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (isBodyMethod && req.body) {
    init.body = req.body;
    init.duplex = "half";
  }

  try {
    const upstream = await fetch(targetUrl, init);
    const outHeaders = new Headers();
    for (const [k, v] of upstream.headers.entries()) {
      const low = k.toLowerCase();
      if (low === "transfer-encoding" || low === "connection" || low === "content-encoding") continue;
      outHeaders.set(k, v);
    }
    if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
      outHeaders.set("Cache-Control", "no-cache, no-transform");
      outHeaders.set("X-Accel-Buffering", "no");
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: outHeaders,
    });
  } catch (err) {
    return Response.json(
      {
        detail: `No se pudo conectar con clipsserver en ${SERVER_BASE}. Inicia el servidor con '.venv\\Scripts\\clipsserver.exe serve'. (${String(err)})`,
      },
      { status: 502 }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
export const HEAD = proxyRequest;
