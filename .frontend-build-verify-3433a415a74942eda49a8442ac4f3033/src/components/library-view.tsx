"use client";

import { useMemo, useState } from "react";
import { Grid2X2, List, LoaderCircle, Search, SlidersHorizontal, Video } from "lucide-react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useVideos } from "@/hooks/use-videos";
import type { VideoRecord } from "@/lib/types";
import { VideoCard } from "@/components/video-card";

type Filter = "all" | "ready" | "processing" | "failed";
type Sort = "recent" | "updated" | "duration" | "title";

export function LibraryView({ initialQuery = "", compact = false }: { initialQuery?: string; compact?: boolean }) {
  const { videos, isLoading, error, refresh, remove } = useVideos();
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [deleting, setDeleting] = useState<string | null>(null);

  const filteredVideos = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matchesFilter = (video: VideoRecord) => {
      if (filter === "all") return true;
      if (filter === "processing") return ["queued", "downloading", "transcribing", "chunking", "embedding"].includes(video.status);
      return video.status === filter;
    };
    return videos.filter((video) => {
      const searchable = `${video.title} ${video.channel ?? ""}`.toLowerCase();
      return matchesFilter(video) && (!needle || searchable.includes(needle));
    }).sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "duration") return b.duration_seconds - a.duration_seconds;
      const field = sort === "updated" ? "updated_at" : "created_at";
      return new Date(b[field]).getTime() - new Date(a[field]).getTime();
    });
  }, [filter, query, sort, videos]);

  const counts = useMemo(() => ({
    all: videos.length,
    ready: videos.filter((video) => video.status === "ready").length,
    processing: videos.filter((video) => ["queued", "downloading", "transcribing", "chunking", "embedding"].includes(video.status)).length,
    failed: videos.filter((video) => video.status === "failed").length,
  }), [videos]);

  const confirmDelete = async (video: VideoRecord) => {
    if (!window.confirm(`Delete “${video.title}”? This removes its transcript and index.`)) return;
    setDeleting(video.video_id);
    try {
      await remove(video.video_id);
    } catch (reason) {
      window.alert(reason instanceof ApiError ? reason.message : "Unable to delete this video.");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <section className={`library-section ${compact ? "library-compact" : ""}`}>
      <div className="section-heading library-heading">
        <div><p className="eyebrow">Your learning space</p><h1>{compact ? "Your Library" : "Video library"}</h1><p>{videos.length} indexed video{videos.length === 1 ? "" : "s"} across your workspace.</p></div>
        {!compact && <button type="button" className="button button-secondary" onClick={() => router.push("/uploads")}>Add a video</button>}
      </div>
      <div className="library-toolbar" aria-label="Library controls">
        <div className="filter-tabs" role="tablist" aria-label="Video status">
          {(["all", "ready", "processing", "failed"] as Filter[]).map((name) => <button type="button" role="tab" aria-selected={filter === name} key={name} onClick={() => setFilter(name)} className={filter === name ? "selected" : ""}>{name[0].toUpperCase() + name.slice(1)} <span>{counts[name]}</span></button>)}
        </div>
        <div className="library-tools">
          <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search in your library" aria-label="Search in your library" /></label>
          <label className="select-field"><SlidersHorizontal size={15} /><span className="sr-only">Sort videos</span><select value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="recent">Recently added</option><option value="updated">Recently updated</option><option value="duration">Duration</option><option value="title">Title</option></select></label>
          <div className="view-switch" aria-label="Library view"><button type="button" aria-label="Grid view" className={view === "grid" ? "selected" : ""} onClick={() => setView("grid")}><Grid2X2 size={17} /></button><button type="button" aria-label="List view" className={view === "list" ? "selected" : ""} onClick={() => setView("list")}><List size={18} /></button></div>
        </div>
      </div>
      {isLoading ? <LibrarySkeleton /> : error ? <div className="inline-state error-state"><p>{error}</p><button type="button" className="button button-secondary button-small" onClick={() => void refresh()}>Try again</button></div> : filteredVideos.length === 0 ? <EmptyLibrary hasVideos={videos.length > 0} /> : <div className={`video-grid ${view === "list" ? "video-list" : ""}`}>{filteredVideos.map((video) => <VideoCard key={video.video_id} video={video} view={view} onDelete={confirmDelete} />)}</div>}
      {deleting && <p className="operation-toast"><LoaderCircle size={16} className="spin" /> Deleting video…</p>}
    </section>
  );
}

function LibrarySkeleton() {
  return <div className="video-grid" aria-label="Loading library">{Array.from({ length: 6 }, (_, index) => <div className="video-card skeleton-card" key={index}><div className="skeleton video-skeleton" /><div className="video-card-body"><div className="skeleton skeleton-line wide" /><div className="skeleton skeleton-line" /><div className="skeleton skeleton-line short" /></div></div>)}</div>;
}

function EmptyLibrary({ hasVideos }: { hasVideos: boolean }) {
  const router = useRouter();
  return <div className="empty-state"><span className="empty-icon"><Video size={26} /></span><h2>{hasVideos ? "No matching videos" : "No videos yet"}</h2><p>{hasVideos ? "Try a different search or filter." : "Import your first video to start asking grounded questions."}</p>{!hasVideos && <button type="button" className="button button-primary" onClick={() => router.push("/uploads")}>Import a video</button>}</div>;
}
