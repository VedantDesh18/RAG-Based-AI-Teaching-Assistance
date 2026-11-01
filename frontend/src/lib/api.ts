import type {
  ChatMessage,
  ChatSession,
  Citation,
  Health,
  Job,
  JobStart,
  TranscriptSegment,
  VideoRecord,
} from "@/lib/types";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "";

function endpoint(path: string) {
  return `${API_ROOT}${path}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const issues = detail.map((item) => {
      if (!item || typeof item !== "object") return null;
      const issue = item as { loc?: unknown; msg?: unknown };
      const location = Array.isArray(issue.loc)
        ? issue.loc.filter((part) => part !== "body").map(String).join(".")
        : "";
      const message = typeof issue.msg === "string" ? issue.msg : "Invalid request";
      return location ? `${location}: ${message}` : message;
    }).filter((item): item is string => Boolean(item));
    if (issues.length) return issues.join("; ");
  }
  return null;
}

async function errorMessage(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown; message?: unknown };
    return formatDetail(body.detail) ?? formatDetail(body.message) ?? "The request could not be completed.";
  } catch {
    return "The request could not be completed.";
  }
}

function isJobStart(value: unknown): value is JobStart {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return typeof result.job_id === "string"
    && typeof result.video_id === "string"
    && typeof result.status === "string";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(endpoint(path), { ...init, headers: { Accept: "application/json", ...init?.headers } });
  } catch {
    throw new ApiError("VideoQA backend is unavailable. Check the connection and try again.");
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  videos: async () => {
    const result = await request<{ videos: VideoRecord[]; total: number } | VideoRecord[]>("/api/videos");
    return Array.isArray(result) ? result : result.videos;
  },
  video: (id: string) => request<VideoRecord>(`/api/videos/${encodeURIComponent(id)}`),
  transcript: async (id: string) => {
    const result = await request<{ segments: TranscriptSegment[] }>(`/api/videos/${encodeURIComponent(id)}/transcript`);
    return result.segments;
  },
  removeVideo: (id: string) => request<{ deleted: boolean }>(`/api/videos/${encodeURIComponent(id)}`, { method: "DELETE" }),
  ingestUrl: (url: string) => request<JobStart>("/api/ingest/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  }),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) => request<JobStart>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  retryJob: (id: string) => request<JobStart>(`/api/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  chats: async () => {
    const result = await request<{ sessions: ChatSession[] }>("/api/chats");
    return result.sessions;
  },
  chat: (id: string) => request<{ session: ChatSession; messages: ChatMessage[] }>(`/api/chats/${encodeURIComponent(id)}`),
};

export function uploadVideo(
  file: File,
  onProgress: (uploadedBytes: number, totalBytes: number) => void,
): { promise: Promise<JobStart>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<JobStart>((resolve, reject) => {
    xhr.open("POST", endpoint("/api/ingest/file"));
    // Read text and parse explicitly so non-JSON proxy errors and FastAPI's
    // structured 422 validation details are both surfaced to the user.
    xhr.responseType = "text";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    };
    xhr.onerror = () => {
      // #region agent log
      fetch("http://127.0.0.1:7306/ingest/2502a175-f3c0-451f-8de0-1648841abc44",{method:"POST",headers:{"Content-Type":"application/json","X-Debug-Session-Id":"1ba419"},body:JSON.stringify({sessionId:"1ba419",runId:"pre-fix",hypothesisId:"A",location:"frontend/src/lib/api.ts:xhr.onerror",message:"XHR network error before HTTP status",data:{readyState:xhr.readyState},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      reject(new ApiError("VideoQA backend is unavailable. Check the connection and try again."));
    };
    xhr.onabort = () => reject(new ApiError("Upload cancelled."));
    xhr.onload = () => {
      const responseText = typeof xhr.response === "string" ? xhr.response : "";
      let data: unknown = null;
      try { data = responseText ? JSON.parse(responseText) : null; } catch { /* handled below */ }
      // #region agent log
      fetch("http://127.0.0.1:7306/ingest/2502a175-f3c0-451f-8de0-1648841abc44",{method:"POST",headers:{"Content-Type":"application/json","X-Debug-Session-Id":"1ba419"},body:JSON.stringify({sessionId:"1ba419",runId:"pre-fix",hypothesisId:"A,C,D",location:"frontend/src/lib/api.ts:xhr.onload",message:"Upload XHR completed",data:{status:xhr.status,contentType:xhr.getResponseHeader("content-type"),responsePrefix:responseText.slice(0,180),parsedJson:Boolean(data && typeof data === "object"),fileName:file.name,fileSize:file.size,fileType:file.type},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      if (xhr.status >= 200 && xhr.status < 300) {
        if (isJobStart(data)) resolve(data);
        else reject(new ApiError("The server returned an invalid upload response.", xhr.status));
        return;
      }
      const body = data && typeof data === "object" ? data as { detail?: unknown; message?: unknown } : {};
      const detail = formatDetail(body.detail) ?? formatDetail(body.message);
      reject(new ApiError(detail ?? `Upload failed (HTTP ${xhr.status || "unknown"}).`, xhr.status));
    };
    const form = new FormData();
    form.append("file", file);
    // #region agent log
    fetch("http://127.0.0.1:7306/ingest/2502a175-f3c0-451f-8de0-1648841abc44",{method:"POST",headers:{"Content-Type":"application/json","X-Debug-Session-Id":"1ba419"},body:JSON.stringify({sessionId:"1ba419",runId:"pre-fix",hypothesisId:"A,D",location:"frontend/src/lib/api.ts:xhr.send",message:"Sending multipart upload without manual Content-Type",data:{endpoint:endpoint("/api/ingest/file"),fieldName:"file",fileName:file.name,fileSize:file.size,fileType:file.type,apiRoot:API_ROOT || "(same-origin)"},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    xhr.send(form);
  });
  return { promise, cancel: () => xhr.abort() };
}

export async function streamAnswer(
  payload: { question: string; video_id?: string; session_id?: string },
  callbacks: {
    onMeta: (data: { grounded: boolean; session_id: string }) => void;
    onToken: (text: string) => void;
    onDone: (data: { citations: Citation[]; session_id: string }) => void;
    onError: (message: string) => void;
  },
  signal?: AbortSignal,
) {
  const response = await fetch(endpoint("/api/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  if (!response.body) throw new ApiError("No response stream was returned.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const consumeEvent = (raw: string) => {
    const lines = raw.split("\n");
    const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() ?? "message";
    const dataLine = lines.find((line) => line.startsWith("data:"));
    if (!dataLine) return;
    try {
      const data = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>;
      if (name === "meta") callbacks.onMeta(data as { grounded: boolean; session_id: string });
      if (name === "token") callbacks.onToken(String(data.text ?? ""));
      if (name === "done") callbacks.onDone(data as { citations: Citation[]; session_id: string });
      if (name === "error") callbacks.onError(String(data.message ?? "Unable to complete the answer."));
    } catch {
      // A malformed SSE frame cannot be safely rendered as an answer.
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    frames.forEach(consumeEvent);
    if (done) break;
  }
  if (buffer.trim()) consumeEvent(buffer);
}
