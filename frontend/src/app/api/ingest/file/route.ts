import http from "node:http";
import https from "node:https";
import { Readable } from "node:stream";
import { URL } from "node:url";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 3600;

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

function debugLog(message: string, data: Record<string, unknown>) {
  // #region agent log
  const payload = {
    sessionId: "1ba419",
    runId: "post-fix",
    hypothesisId: "A,C",
    location: "frontend/src/app/api/ingest/file/route.ts",
    message,
    data,
    timestamp: Date.now(),
  };
  const body = JSON.stringify(payload);
  const headers = { "Content-Type": "application/json", "X-Debug-Session-Id": "1ba419" };
  fetch("http://127.0.0.1:7306/ingest/2502a175-f3c0-451f-8de0-1648841abc44", { method: "POST", headers, body }).catch(() => {});
  fetch("http://host.docker.internal:7306/ingest/2502a175-f3c0-451f-8de0-1648841abc44", { method: "POST", headers, body }).catch(() => {});
  // #endregion
}

function unavailableResponse() {
  return Response.json({
    success: false,
    message: "Unable to reach the VideoQA backend for upload.",
    error_code: "BACKEND_UNAVAILABLE",
    detail: "Unable to reach the VideoQA backend for upload.",
  }, { status: 502 });
}

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") || "";
  const contentLength = request.headers.get("content-length");
  debugLog("Streaming multipart upload to FastAPI", {
    backend: BACKEND_URL,
    contentTypePrefix: contentType.slice(0, 80),
    contentLength,
    hasBody: Boolean(request.body),
  });

  if (!request.body) {
    return Response.json({
      success: false,
      message: "The upload request did not include a file body.",
      error_code: "EMPTY_UPLOAD",
      detail: "The upload request did not include a file body.",
    }, { status: 400 });
  }

  let target: URL;
  try {
    target = new URL("/api/ingest/file", BACKEND_URL);
  } catch {
    return unavailableResponse();
  }

  const transport = target.protocol === "https:" ? https : http;
  const incoming = request.body;

  return new Promise<Response>((resolve) => {
    const upstream = transport.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === "https:" ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method: "POST",
      headers: {
        accept: request.headers.get("accept") || "application/json",
        "content-type": contentType,
        ...(contentLength ? { "content-length": contentLength } : {}),
      },
    }, (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      response.on("end", () => {
        const headers = new Headers();
        for (const [key, value] of Object.entries(response.headers)) {
          if (key === "transfer-encoding" || key === "connection") continue;
          if (typeof value === "string") headers.set(key, value);
          else if (Array.isArray(value)) headers.set(key, value.join(", "));
        }
        debugLog("Upstream ingest response", {
          status: response.statusCode || 502,
          upstreamType: headers.get("content-type"),
          bodyBytes: Buffer.concat(chunks).byteLength,
        });
        resolve(new Response(Buffer.concat(chunks), {
          status: response.statusCode || 502,
          headers,
        }));
      });
    });

    upstream.on("error", (error) => {
      debugLog("Upload proxy failed to reach backend", {
        error: error.message.slice(0, 300),
        contentLength,
      });
      resolve(unavailableResponse());
    });

    Readable.fromWeb(incoming as import("node:stream/web").ReadableStream).pipe(upstream);
  });
}
