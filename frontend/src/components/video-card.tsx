"use client";

import Link from "next/link";
import { EllipsisVertical, MessageSquareText, Play, Trash2, Video } from "lucide-react";
import { formatDate, formatDuration, displayStatus } from "@/lib/format";
import type { VideoRecord } from "@/lib/types";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{displayStatus(status)}</span>;
}

export function VideoCard({ video, view = "grid", onDelete }: { video: VideoRecord; view?: "grid" | "list"; onDelete: (video: VideoRecord) => void }) {
  const chatHref = `/video/${encodeURIComponent(video.video_id)}`;
  const ready = video.status === "ready";
  return (
    <article className={`video-card ${view === "list" ? "video-row" : ""}`}>
      <Link href={ready ? chatHref : "/uploads"} className="video-cover" aria-label={`Open ${video.title}`}>
        {video.thumbnail_url ? <img src={video.thumbnail_url} alt="" /> : <div className="video-placeholder"><Video size={32} aria-hidden="true" /></div>}
        <span className="video-cover-overlay"><Play size={18} fill="currentColor" aria-hidden="true" /></span>
        {video.duration_seconds > 0 && <span className="duration-pill">{formatDuration(video.duration_seconds)}</span>}
      </Link>
      <div className="video-card-body">
        <div className="video-title-line">
          <Link href={ready ? chatHref : "/uploads"} className="video-title">{video.title}</Link>
          <button type="button" className="icon-button compact" aria-label={`More actions for ${video.title}`}><EllipsisVertical size={17} /></button>
        </div>
        <p className="video-meta">{formatDate(video.created_at)} · {video.chunk_count ?? 0} transcript chunks</p>
        <div className="video-actions">
          <StatusBadge status={video.status} />
          <div className="video-action-buttons">
            <button type="button" className="icon-button compact danger" onClick={() => onDelete(video)} aria-label={`Delete ${video.title}`}><Trash2 size={16} /></button>
            {ready ? <Link href={chatHref} className="button button-secondary button-small"><MessageSquareText size={15} /> Chat</Link> : <span className="processing-copy">{displayStatus(video.status)}</span>}
          </div>
        </div>
      </div>
    </article>
  );
}
