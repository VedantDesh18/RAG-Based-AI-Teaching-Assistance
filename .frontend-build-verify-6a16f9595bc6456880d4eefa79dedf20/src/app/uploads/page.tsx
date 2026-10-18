"use client";

import { FileVideo, ShieldCheck, Sparkles } from "lucide-react";
import { IngestionPanel } from "@/components/ingestion-panel";

export default function UploadsPage() {
  return <div className="page-stack">
    <section className="page-intro"><p className="eyebrow">Ingestion workspace</p><h1>Add a video</h1><p>Import a public YouTube link or upload a local lecture, meeting, or recording. Processing happens in your configured local pipeline.</p></section>
    <IngestionPanel />
    <section className="info-grid">
      <article><FileVideo size={20} /><h2>Supported sources</h2><p>YouTube links and MP4, WebM, MKV, MOV, AVI, MP3, WAV, or M4A uploads up to 2 GB.</p></article>
      <article><Sparkles size={20} /><h2>Caption-first processing</h2><p>Existing captions are used when available; transcription is used only when a transcript is needed.</p></article>
      <article><ShieldCheck size={20} /><h2>Reliable job states</h2><p>Each stage is reported by the backend. Failed jobs can be retried without pretending the work succeeded.</p></article>
    </section>
  </div>;
}
