import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return new Response(
      JSON.stringify({ detail: "Unable to read request body." }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(`${BACKEND_URL}/api/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body,
      // @ts-expect-error Node fetch supports duplex option for streaming
      duplex: "half",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend unavailable";
    return new Response(
      JSON.stringify({ detail: `Unable to connect to VideoQA backend: ${message}` }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  if (!upstreamResponse.ok) {
    const errorText = await upstreamResponse.text();
    return new Response(errorText, {
      status: upstreamResponse.status,
      headers: {
        "Content-Type": upstreamResponse.headers.get("content-type") || "application/json",
      },
    });
  }

  // Stream SSE from backend to client with proper streaming headers
  return new Response(upstreamResponse.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

