export type VideoStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed"
  | "cancelled";

export type VideoRecord = {
  video_id: string;
  source_type: "youtube" | "direct_url" | "file_upload";
  source_url?: string | null;
  title: string;
  channel?: string | null;
  duration_seconds: number;
  thumbnail_url?: string | null;
  upload_date?: string | null;
  description?: string | null;
  detected_language?: string | null;
  file_path?: string | null;
  media_url?: string | null;
  media_available?: boolean;
  status: VideoStatus;
  error_message?: string | null;
  retry_count?: number;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
};

export type Job = {
  job_id: string;
  video_id: string;
  status: VideoStatus;
  stage: VideoStatus;
  stage_index: number | null;
  stages: string[];
  error_message?: string | null;
  retry_count: number;
  created_at?: string;
  updated_at?: string;
};

export type TranscriptSegment = {
  segment_index: number;
  start_seconds: number;
  end_seconds: number;
  text_original?: string | null;
  text_english?: string | null;
  language?: string | null;
};

export type Citation = {
  chunk_id?: string;
  video_id?: string;
  title?: string;
  start_seconds: number;
  end_seconds: number;
  start_display: string;
  end_display: string;
  deeplink?: string | null;
  text_snippet?: string;
  similarity?: number;
};

export type ChatMessage = {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  created_at?: string;
  isStreaming?: boolean;
  error?: boolean;
};

export type ChatSession = {
  session_id: string;
  video_id?: string | null;
  created_at: string;
  updated_at: string;
  video_title?: string | null;
  last_question?: string | null;
  last_answer?: string | null;
};

export type JobStart = {
  job_id: string;
  video_id: string;
  title?: string;
  duration_seconds?: number;
  thumbnail_url?: string | null;
  status: VideoStatus | "already_indexed";
  message?: string;
  retry_count?: number;
};

export type Health = {
  status: "ok" | "degraded";
  services?: Record<string, "ok" | "unavailable" | "missing">;
};
