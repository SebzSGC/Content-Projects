import { NextRequest } from "next/server";

// Streams every /api/worker/* request to the Python worker (worker/). Bodies
// and responses are piped, so multi-GB uploads and video range requests work.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const WORKER_URL = (process.env.CLIPS_WORKER_URL || "http://127.0.0.1:8790").replace(/\/$/, "");

const FORWARDED_REQUEST_HEADERS = ["content-type", "content-length", "range"];
const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-length",
  "content-range",
  "accept-ranges",
  "content-disposition",
  "last-modified",
  "etag",
];

async function proxy(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = new URL(`${WORKER_URL}/${path.map(encodeURIComponent).join("/")}`);
  req.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = !["GET", "HEAD"].includes(req.method);
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (hasBody && req.body) {
    init.body = req.body;
    init.duplex = "half";
  }

  let res: Response;
  try {
    res = await fetch(target, init);
  } catch {
    return Response.json(
      {
        detail:
          "El worker de procesamiento no responde. Inícialo con `gameclips serve` dentro de ClippersIppers/worker.",
      },
      { status: 502 }
    );
  }

  const out = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = res.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
