"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Clock3, MessageSquareText } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ChatSession } from "@/lib/types";

export default function HistoryPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    setLoading(true);
    try { setSessions(await api.chats()); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load chat history."); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  return <div className="page-stack">
    <section className="page-intro"><p className="eyebrow">Your conversations</p><h1>Chat history</h1><p>Continue a saved conversation with the video context and verified evidence intact.</p></section>
    {loading ? <div className="history-list">{Array.from({ length: 4 }, (_, index) => <div className="history-card skeleton" key={index} />)}</div> : error ? <div className="inline-state error-state"><p>{error}</p><button type="button" className="button button-secondary button-small" onClick={() => void load()}>Try again</button></div> : sessions.length === 0 ? <div className="empty-state"><span className="empty-icon"><MessageSquareText size={26} /></span><h2>No conversations yet</h2><p>Open a ready video and ask your first question to save a chat here.</p><Link href="/library" className="button button-primary">Open library</Link></div> : <section className="history-list">{sessions.map((session) => <article className="history-card" key={session.session_id}><span className="history-icon"><MessageSquareText size={19} /></span><div><p className="history-video">{session.video_title || "Library conversation"}</p><h2>{session.last_question || "Conversation started"}</h2><p>{session.last_answer || "No completed assistant message yet."}</p><small><Clock3 size={13} /> Updated {formatDate(session.updated_at)}</small></div>{session.video_id && <Link href={`/video/${encodeURIComponent(session.video_id)}?session=${encodeURIComponent(session.session_id)}`} className="button button-secondary button-small">Continue <ArrowRight size={14} /></Link>}</article>)}</section>}
  </div>;
}
