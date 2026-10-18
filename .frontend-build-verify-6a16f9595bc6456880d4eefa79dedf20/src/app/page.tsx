"use client";

import { BrainCircuit, Languages, MessageSquareText, Quote } from "lucide-react";
import { IngestionPanel } from "@/components/ingestion-panel";
import { LibraryView } from "@/components/library-view";

const features = [
  { icon: MessageSquareText, title: "Chat with videos", copy: "Ask clear questions instead of scrubbing timelines." },
  { icon: Quote, title: "Timestamped citations", copy: "Return to the exact supporting moment." },
  { icon: Languages, title: "Multi-language ready", copy: "Index captions or transcribe local recordings." },
  { icon: BrainCircuit, title: "Grounded answers", copy: "Evidence stays separate from generated text." },
];

export default function HomePage() {
  return <div className="page-stack home-page">
    <section className="hero-section">
      <div className="hero-copy">
        <p className="eyebrow">Video learning, made searchable</p>
        <h1>Turn your videos into <span>conversations.</span></h1>
        <p className="hero-description">Ask questions, get grounded answers, and jump directly to the moment that matters.</p>
      </div>
      <div className="hero-orbit" aria-hidden="true"><span /><span /><span /></div>
    </section>
    <IngestionPanel />
    <section className="feature-grid" aria-label="VideoQA features">
      {features.map(({ icon: Icon, title, copy }, index) => <article key={title} className={`feature-card feature-${index + 1}`}><span className="feature-icon"><Icon size={21} /></span><div><h2>{title}</h2><p>{copy}</p></div></article>)}
    </section>
    <LibraryView compact />
  </div>;
}
