import Link from "next/link";
import { ArrowRight, MessageSquareText, UploadCloud, MousePointerClick } from "lucide-react";

const steps = [
  { icon: UploadCloud, title: "1. Add a video", copy: "Paste a YouTube URL or upload a supported local file." },
  { icon: MessageSquareText, title: "2. Wait for indexing", copy: "The backend reports its real processing stage as it works." },
  { icon: MousePointerClick, title: "3. Ask and jump", copy: "Use structured evidence chips to seek directly to supporting moments." },
];

export default function HelpPage() {
  return <div className="page-stack"><section className="page-intro"><p className="eyebrow">VideoQA guide</p><h1>Help & documentation</h1><p>VideoQA turns a transcript into a searchable, citation-aware learning workspace while keeping the retrieval pipeline local.</p></section><section id="how-it-works" className="how-it-works">{steps.map(({ icon: Icon, title, copy }) => <article key={title}><span className="feature-icon"><Icon size={21} /></span><h2>{title}</h2><p>{copy}</p></article>)}</section><section className="help-callout"><h2>Need a starting point?</h2><p>Open the library to continue an indexed video, or add a new source from the upload workspace.</p><div><Link href="/library" className="button button-secondary">Open library</Link><Link href="/uploads" className="button button-primary">Add a video <ArrowRight size={15} /></Link></div></section></div>;
}
