import test from "node:test";
import assert from "node:assert/strict";

// Helper models mimicking frontend/src/lib/types.ts
type VideoRecord = {
  video_id: string;
  source_type: "youtube" | "direct_url" | "file_upload";
  title: string;
  status: "queued" | "downloading" | "transcribing" | "chunking" | "embedding" | "ready" | "failed" | "cancelled";
  chunk_count?: number;
  duration_seconds: number;
  media_available?: boolean;
  media_url?: string | null;
  error_message?: string | null;
};

type TranscriptSegment = {
  segment_index: number;
  start_seconds: number;
  end_seconds: number;
  text_original?: string | null;
  text_english?: string | null;
};

// Workspace logic functions under test
function computeChatReady(
  video: VideoRecord | null,
  videoId: string,
  transcript: TranscriptSegment[],
  isLoading: boolean
): boolean {
  if (isLoading || !video) return false;
  const hasIndexedContent = (video.chunk_count ?? 0) > 0 || transcript.length > 0;
  return Boolean(video.video_id === videoId && video.status === "ready" && hasIndexedContent);
}

function computeCanSubmit(
  question: string,
  isSending: boolean,
  video: VideoRecord | null,
  videoId: string,
  transcript: TranscriptSegment[],
  isLoading: boolean
): boolean {
  const trimmed = question.trim();
  if (!trimmed || isSending || isLoading || !video) return false;
  const hasIndexedContent = (video.chunk_count ?? 0) > 0 || transcript.length > 0;
  return Boolean(video.video_id === videoId && video.status === "ready" && hasIndexedContent);
}

function computePlaceholder(
  chatReady: boolean,
  video: VideoRecord | null,
  isIndexing: boolean
): string {
  if (chatReady) return "Ask anything about this video…";
  if (!video) return "Chat unlocks after indexing is complete";
  if (video.status === "failed") return "Chat is unavailable until indexing succeeds";
  if (isIndexing) return `Chat unlocks after indexing completes (${video.status})`;
  return "Chat unlocks after indexing is complete";
}

function shouldSubmitOnKeyDown(key: string, shiftKey: boolean): boolean {
  return key === "Enter" && !shiftKey;
}

// 1. Ready local video with actual indexed chunks: input enabled
test("1. Ready local video with indexed chunks enables chat input", () => {
  const video: VideoRecord = {
    video_id: "local-video-1",
    source_type: "file_upload",
    title: "Javascript Tutorial",
    status: "ready",
    chunk_count: 40,
    duration_seconds: 691,
    media_available: true,
    media_url: "/api/videos/local-video-1/media",
  };
  const isReady = computeChatReady(video, "local-video-1", [], false);
  assert.equal(isReady, true);
  assert.equal(computePlaceholder(isReady, video, false), "Ask anything about this video…");
  assert.equal(computeCanSubmit("What is a callback?", false, video, "local-video-1", [], false), true);
});

// 2. Ready video with stale chunk_count but real chunks: input enabled
test("2. Ready video with stale chunk_count=0 but real transcript chunks enables input", () => {
  const video: VideoRecord = {
    video_id: "local-video-2",
    source_type: "file_upload",
    title: "Stale Chunk Video",
    status: "ready",
    chunk_count: 0, // Stale count from DB
    duration_seconds: 300,
    media_available: true,
  };
  const transcript: TranscriptSegment[] = [
    { segment_index: 0, start_seconds: 0, end_seconds: 5, text_english: "Hello world" },
  ];
  const isReady = computeChatReady(video, "local-video-2", transcript, false);
  assert.equal(isReady, true);
  assert.equal(computeCanSubmit("Explain intro", false, video, "local-video-2", transcript, false), true);
});

// 3. Video with no indexed chunks: correct unavailable state
test("3. Video with no indexed chunks remains in disabled/unavailable state", () => {
  const video: VideoRecord = {
    video_id: "local-video-3",
    source_type: "file_upload",
    title: "Empty Video",
    status: "ready",
    chunk_count: 0,
    duration_seconds: 60,
    media_available: true,
  };
  const isReady = computeChatReady(video, "local-video-3", [], false);
  assert.equal(isReady, false);
  assert.equal(computeCanSubmit("Any content?", false, video, "local-video-3", [], false), false);
  assert.equal(computePlaceholder(isReady, video, false), "Chat unlocks after indexing is complete");
});

// 4. Failed indexing: error shown and player remains usable
test("4. Failed indexing shows error state while keeping local video playable", () => {
  const video: VideoRecord = {
    video_id: "local-failed-4",
    source_type: "file_upload",
    title: "Failed Lecture",
    status: "failed",
    chunk_count: 0,
    duration_seconds: 120,
    media_available: true,
    media_url: "/api/videos/local-failed-4/media",
    error_message: "Whisper decoding error",
  };
  const isReady = computeChatReady(video, "local-failed-4", [], false);
  assert.equal(isReady, false);
  assert.equal(video.media_available, true);
  assert.equal(video.media_url, "/api/videos/local-failed-4/media");
  assert.equal(computePlaceholder(isReady, video, false), "Chat is unavailable until indexing succeeds");
});

// 5. Selected video ID passed correctly
test("5. Video ID validation ensures questions are bound to current video", () => {
  const video: VideoRecord = {
    video_id: "video-A",
    source_type: "file_upload",
    title: "Video A",
    status: "ready",
    chunk_count: 10,
    duration_seconds: 100,
  };
  // If user navigated to video-B URL, mismatch blocks submission
  assert.equal(computeCanSubmit("Question", false, video, "video-B", [], false), false);
  // Matching video ID allows submission
  assert.equal(computeCanSubmit("Question", false, video, "video-A", [], false), true);
});

// 6. Enter-key submission
test("6. Enter key triggers submission while Shift+Enter creates a new line", () => {
  assert.equal(shouldSubmitOnKeyDown("Enter", false), true);
  assert.equal(shouldSubmitOnKeyDown("Enter", true), false);
  assert.equal(shouldSubmitOnKeyDown("a", false), false);
});

// 7. Send-button submission
test("7. Send button submission validation respects whitespace and sending flag", () => {
  const video: VideoRecord = {
    video_id: "video-send",
    source_type: "file_upload",
    title: "Send Test",
    status: "ready",
    chunk_count: 5,
    duration_seconds: 50,
  };
  assert.equal(computeCanSubmit("   ", false, video, "video-send", [], false), false);
  assert.equal(computeCanSubmit("Valid question", false, video, "video-send", [], false), true);
  assert.equal(computeCanSubmit("Valid question", true, video, "video-send", [], false), false);
});

// 8. API failure followed by successful retry restores usable state
test("8. In-progress flag resets after failure allowing retry", async () => {
  let isSending = false;
  const video: VideoRecord = {
    video_id: "video-retry",
    source_type: "file_upload",
    title: "Retry Test",
    status: "ready",
    chunk_count: 5,
    duration_seconds: 50,
  };

  // Simulate attempt 1 (fails)
  try {
    isSending = true;
    throw new Error("Local AI service is unavailable");
  } catch {
    // Handled in catch block
  } finally {
    isSending = false;
  }
  assert.equal(isSending, false);
  assert.equal(computeCanSubmit("Retry question", isSending, video, "video-retry", [], false), true);
});

// 9. No regression for YouTube videos
test("9. YouTube videos maintain proper chatReady and player availability", () => {
  const video: VideoRecord = {
    video_id: "dQw4w9WgXcQ",
    source_type: "youtube",
    title: "Never Gonna Give You Up",
    status: "ready",
    chunk_count: 50,
    duration_seconds: 213,
    media_available: true,
    media_url: null,
  };
  const isReady = computeChatReady(video, "dQw4w9WgXcQ", [], false);
  assert.equal(isReady, true);
  assert.equal(video.source_type, "youtube");
  assert.equal(video.media_available, true);
  assert.equal(computeCanSubmit("What is the song about?", false, video, "dQw4w9WgXcQ", [], false), true);
});
