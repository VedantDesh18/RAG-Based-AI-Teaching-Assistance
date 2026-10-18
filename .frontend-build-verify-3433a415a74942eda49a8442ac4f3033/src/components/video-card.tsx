"use client";

import Link from "next/link";
import { useState } from "react";
import { EllipsisVertical, MessageSquareText, Play, Trash2, Video } from "lucide-react";
import { formatDate, formatDuration, displayStatus } from "@/lib/format";
import { api } from "@/lib/api";
import type { VideoRecord } from "@/lib/types";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{displayStatus(status)}</span>;
}

export function VideoCard({ video, view = "grid", onDelete }: { video: VideoRecord; view?: "grid" | "list"; onDelete: (video: VideoRecord) => void }) {
  const chatHref = `/video/${encodeURIComponent(video.video_id)}`;
  const chatReady = video.status === "ready" && (video.chunk_count ?? 0) > 0;
  const mediaAvailable = video.media_available ?? (video.source_type === "youtube" || Boolean(video.media_url || video.file_path));
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const retry = async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      await api.retryJob(video.video_id);
      window.dispatchEvent(new Event("videoqa:videos-changed"));
    } catch (reason) {
      setRetryError(reason instanceof Error ? reason.message : "Unable to retry indexing.");
    } finally {
      setRetrying(false);
    }
  };
  return (
    <article className={`video-card ${view === "list" ? "video-row" : ""}`}>
      <Link href={chatHref} className="video-cover" aria-label={`Open ${video.title}`}>
        {video.thumbnail_url ? <img src={video.thumbnail_url} alt="" /> : <div className="video-placeholder"><Video size={32} aria-hidden="true" /></div>}
        <span className="video-cover-overlay">{mediaAvailable ? <Play size={18} fill="currentColor" aria-hidden="true" /> : <Video size={18} aria-hidden="true" />}</span>
        {video.duration_seconds > 0 && <span className="duration-pill">{formatDuration(video.duration_seconds)}</span>}
      </Link>
      <div className="video-card-body">
        <div className="video-title-line">
          <Link href={chatHref} className="video-title">{video.title}</Link>
          <button type="button" className="icon-button compact" aria-label={`More actions for ${video.title}`}><EllipsisVertical size={17} /></button>
        </div>
        <p className="video-meta">{formatDate(video.created_at)} · {video.chunk_count ?? 0} transcript chunks</p>
        {video.source_type === "file_upload" && !mediaAvailable && <p className="video-error">Source file is missing. Playback is unavailable.</p>}
        {video.status === "failed" && video.error_message && <p className="video-error" role="status">{video.error_message}</p>}
        {retryError && <p className="video-error" role="alert">{retryError}</p>}
        <div className="video-actions">
          <StatusBadge status={video.status} />
          <div className="video-action-buttons">
            <button type="button" className="icon-button compact danger" onClick={() => onDelete(video)} aria-label={`Delete ${video.title}`}><Trash2 size={16} /></button>
            {chatReady ? <Link href={chatHref} className="button button-secondary button-small"><MessageSquareText size={15} /> Chat</Link> : <span className="processing-copy">{video.status === "ready" ? "Transcript unavailable" : displayStatus(video.status)}</span>}
            {!chatReady && (video.status === "queued" || video.status === "downloading" || video.status === "transcribing" || video.status === "chunking" || video.status === "embedding") && mediaAvailable && <span className="processing-copy">Playable while indexing</span>}
            {(video.status === "failed" || video.status === "cancelled") && mediaAvailable && <button type="button" className="button button-secondary button-small" onClick={() => void retry()} disabled={retrying || (video.retry_count ?? 0) >= 3}>{retrying ? "Retrying…" : "Retry indexing"}</button>}
          </div>
        </div>
      </div>
    </article>
  );
}
