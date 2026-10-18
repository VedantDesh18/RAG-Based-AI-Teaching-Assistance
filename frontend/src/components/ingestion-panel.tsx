"use client";

import { ChangeEvent, DragEvent, FormEvent, useCallback, useRef, useState } from "react";
import { CheckCircle2, FileVideo, Link2, LoaderCircle, RotateCcw, UploadCloud, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useIngestion } from "@/hooks/use-ingestion";
import { useJobStatus } from "@/hooks/use-job-status";
import { displayStatus } from "@/lib/format";
import type { Job, JobStart } from "@/lib/types";

const SUPPORTED_EXTENSIONS = [".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".m4a"];
const MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024;
const STAGES = ["downloading", "transcribing", "chunking", "embedding", "ready"];

export function IngestionPanel({ onChanged }: { onChanged?: () => void }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [activeJob, setActiveJob] = useState<JobStart | null>(null);
  const [isDropping, setIsDropping] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const notifyChanged = useCallback(() => {
    window.dispatchEvent(new Event("videoqa:videos-changed"));
    onChanged?.();
  }, [onChanged]);
  const onStart = useCallback((job: JobStart) => {
    setActiveJob(job);
    notifyChanged();
    if (job.status === "already_indexed") router.push(`/video/${encodeURIComponent(job.video_id)}`);
  }, [notifyChanged, router]);
  const ingestion = useIngestion(onStart);
  const onTerminal = useCallback((job: Job) => { if (job.status === "ready") notifyChanged(); }, [notifyChanged]);
  const { job: liveJob, error: pollingError } = useJobStatus(activeJob?.status === "already_indexed" ? null : activeJob?.job_id ?? null, onTerminal);
  const processing = Boolean(ingestion.upload || (liveJob && !["ready", "failed", "cancelled"].includes(liveJob.status)));
  const error = ingestion.error ?? pollingError ?? liveJob?.error_message ?? null;

  const submitUrl = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setActiveJob(null);
    try { await ingestion.startUrl(url.trim()); } catch { /* state is shown in the card */ }
  };
  const validateAndUpload = async (file?: File) => {
    if (!file) return;
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!SUPPORTED_EXTENSIONS.includes(extension)) {
      window.alert(`Unsupported file type. Use ${SUPPORTED_EXTENSIONS.join(", ")}.`);
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      window.alert("This file exceeds the 2 GB upload limit.");
      return;
    }
    setActiveJob(null);
    try { await ingestion.startFile(file); } catch { /* state is shown in the card */ }
  };
  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => { void validateAndUpload(event.target.files?.[0]); event.target.value = ""; };
  const onDrop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setIsDropping(false); void validateAndUpload(event.dataTransfer.files?.[0]); };
  const retry = async () => {
    if (!activeJob) return;
    try {
      const job = await api.retryJob(activeJob.job_id);
      setActiveJob(job);
    } catch (reason) { window.alert(reason instanceof Error ? reason.message : "Unable to retry this job."); }
  };
  const cancel = async () => {
    if (ingestion.upload) { ingestion.cancel(); return; }
    if (!activeJob) return;
    try { const job = await api.cancelJob(activeJob.job_id); setActiveJob(job); } catch (reason) { window.alert(reason instanceof Error ? reason.message : "Unable to cancel this job."); }
  };

  return <section className="ingestion-section" aria-label="Import a video">
    <div className="ingestion-grid">
      <form className="ingest-card" onSubmit={submitUrl}>
        <span className="feature-icon feature-indigo"><Link2 size={23} /></span>
        <div><h2>Import YouTube URL</h2><p>Paste a public video link to index its transcript.</p></div>
        <label className="url-input"><span className="youtube-dot" aria-hidden="true">▶</span><input type="url" required value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://youtube.com/watch?v=…" aria-label="YouTube video URL" /><button className="button button-primary" type="submit" disabled={processing}>{processing && ingestion.source === "url" ? <LoaderCircle size={16} className="spin" /> : null}Import</button></label>
      </form>
      <div className="ingest-card upload-card">
        <span className="feature-icon feature-mint"><UploadCloud size={23} /></span>
        <div><h2>Upload local video</h2><p>Drop a recording or browse files from your device.</p></div>
        <div className={`drop-zone ${isDropping ? "is-dropping" : ""}`} onDragOver={(event) => { event.preventDefault(); setIsDropping(true); }} onDragLeave={() => setIsDropping(false)} onDrop={onDrop} onClick={() => inputRef.current?.click()} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }} aria-label="Upload a local video">
          <input ref={inputRef} type="file" hidden accept={SUPPORTED_EXTENSIONS.join(",")} onChange={onFileChange} />
          <UploadCloud size={25} /><strong>Drag & drop a video here</strong><span>or click to browse · {SUPPORTED_EXTENSIONS.slice(0, 5).join(", ").toUpperCase()}</span>
        </div>
      </div>
    </div>
    {(activeJob || ingestion.upload || error) && <JobProgress job={liveJob} pending={activeJob} upload={ingestion.upload} error={error} onRetry={retry} onCancel={cancel} onOpen={() => activeJob && router.push(`/video/${encodeURIComponent(activeJob.video_id)}`)} />}
  </section>;
}

function JobProgress({ job, pending, upload, error, onRetry, onCancel, onOpen }: { job: Job | null; pending: JobStart | null; upload: { loaded: number; total: number } | null; error: string | null; onRetry: () => void; onCancel: () => void; onOpen: () => void }) {
  const uploadFailed = Boolean(error && !job && !pending && !upload);
  const status = job?.status ?? pending?.status ?? "queued";
  const terminal = uploadFailed || ["ready", "failed", "cancelled", "already_indexed"].includes(status);
  const uploadPercent = upload && upload.total ? Math.round((upload.loaded / upload.total) * 100) : 0;
  return <div className={`job-panel ${error || status === "failed" ? "has-error" : ""}`} role={error ? "alert" : "status"}>
    <div className="job-panel-heading">
      <div>{status === "ready" || status === "already_indexed" ? <CheckCircle2 className="job-state-icon success" /> : error || status === "failed" ? <XCircle className="job-state-icon failure" /> : <LoaderCircle className="job-state-icon spin" />}<div><strong>{upload ? `Uploading ${uploadPercent}%` : uploadFailed ? "Upload failed" : status === "ready" ? "Ready to chat" : status === "already_indexed" ? "Already indexed" : `${displayStatus(status)} your video`}</strong><p>{error ?? (upload ? "Your file is being transferred to the local backend." : "Stages update only when the backend confirms them.")}</p></div></div>
      <div className="job-actions">{!terminal && <button type="button" className="button button-ghost button-small" onClick={onCancel}>Cancel</button>}{(status === "failed" || status === "cancelled") && <button type="button" className="button button-secondary button-small" onClick={onRetry}><RotateCcw size={14} /> Retry</button>}{(status === "ready" || status === "already_indexed") && <button type="button" className="button button-primary button-small" onClick={onOpen}>Open video</button>}</div>
    </div>
    {upload ? <div className="upload-progress"><div><span>Upload progress</span><strong>{uploadPercent}%</strong></div><progress max={upload.total} value={upload.loaded} /></div> : !uploadFailed && <ol className="stage-list" aria-label="Processing stages">{STAGES.map((stage) => <li key={stage} className={status === stage ? "current" : status === "ready" ? "complete" : ""}><span>{status === "ready" || status === stage ? <CheckCircle2 size={15} /> : <span />}</span>{displayStatus(stage)}</li>)}</ol>}
  </div>;
}
