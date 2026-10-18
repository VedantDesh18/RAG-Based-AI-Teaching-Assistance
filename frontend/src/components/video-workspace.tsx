"use client";

import { FormEvent, KeyboardEvent, RefObject, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Clock3,
  PauseCircle,
  RotateCcw,
  Send,
  Sparkles,
  Subtitles,
  VideoOff,
} from "lucide-react";
import { api, ApiError, streamAnswer } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { ChatMessage, Citation, TranscriptSegment, VideoRecord } from "@/lib/types";

function messageId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export function VideoWorkspace({ videoId, initialSessionId }: { videoId: string; initialSessionId?: string | null }) {
  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId ?? undefined);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const youtubeRef = useRef<HTMLIFrameElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setLoadError(null);
    Promise.all([api.video(videoId), api.transcript(videoId), initialSessionId ? api.chat(initialSessionId) : Promise.resolve(null)])
      .then(([nextVideo, segments, history]) => {
        if (!active) return;
        setVideo(nextVideo);
        setTranscript(segments);
        if (history) {
          setSessionId(history.session.session_id);
          setMessages(history.messages.map((message) => ({ ...message, id: message.id ?? messageId() })));
        } else {
          setMessages([]);
          setSessionId(undefined);
        }
      })
      .catch((reason) => {
        if (active) setLoadError(reason instanceof ApiError ? reason.message : "Unable to load this video.");
      })
      .finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; controllerRef.current?.abort(); };
  }, [initialSessionId, videoId]);

  const isIndexing = Boolean(video && ["queued", "downloading", "transcribing", "chunking", "embedding"].includes(video.status));
  useEffect(() => {
    if (!isIndexing) return;
    const timer = window.setInterval(() => {
      void Promise.all([api.video(videoId), api.transcript(videoId)]).then(([updated, segments]) => {
        setVideo(updated);
        setTranscript(segments);
        window.dispatchEvent(new Event("videoqa:videos-changed"));
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [isIndexing, videoId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: isSending ? "smooth" : "auto", block: "end" });
  }, [isSending, messages]);

  const seek = (seconds: number) => {
    setHighlight(seconds);
    if (video?.source_type === "youtube") {
      const command = (func: string) => youtubeRef.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args: func === "seekTo" ? [seconds, true] : [] }), "*");
      command("seekTo");
      command("playVideo");
    } else if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      void videoRef.current.play().catch(() => undefined);
    }
  };

  const hasIndexedContent = (video?.chunk_count ?? 0) > 0 || transcript.length > 0;
  const chatReady = Boolean(video && video.video_id === videoId && video.status === "ready" && hasIndexedContent);

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const question = input.trim();
    if (!question || isSending || !video || video.video_id !== videoId || video.status !== "ready" || !hasIndexedContent) return;
    const userMessage: ChatMessage = { id: messageId(), role: "user", content: question };
    const assistantId = messageId();
    setMessages((current) => [...current, userMessage, { id: assistantId, role: "assistant", content: "", isStreaming: true }]);
    setInput("");
    setIsSending(true);
    const controller = new AbortController();
    controllerRef.current = controller;
    const changeAssistant = (change: (message: ChatMessage) => ChatMessage) => setMessages((current) => current.map((message) => message.id === assistantId ? change(message) : message));
    try {
      await streamAnswer({ question, video_id: video.video_id, session_id: sessionId }, {
        onMeta: (data) => setSessionId(data.session_id),
        onToken: (token) => changeAssistant((message) => ({ ...message, content: message.content + token })),
        onDone: (data) => {
          setSessionId(data.session_id);
          changeAssistant((message) => ({ ...message, citations: data.citations, isStreaming: false }));
        },
        onError: (message) => changeAssistant((assistant) => ({ ...assistant, content: message, error: true, isStreaming: false })),
      }, controller.signal);
    } catch (reason) {
      if ((reason as Error).name !== "AbortError") {
        const message = reason instanceof ApiError ? reason.message : "Unable to answer this question right now. Please try again.";
        changeAssistant((assistant) => ({ ...assistant, content: message, error: true, isStreaming: false }));
      } else {
        changeAssistant((assistant) => ({ ...assistant, content: assistant.content || "Generation stopped.", isStreaming: false }));
      }
    } finally {
      controllerRef.current = null;
      setIsSending(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); }
  };
  const newChat = () => { controllerRef.current?.abort(); setMessages([]); setSessionId(undefined); setInput(""); };

  if (isLoading) return <WorkspaceSkeleton />;
  if (loadError || !video) return <div className="workspace-state"><CircleAlert size={26} /><h1>We couldn’t load this video.</h1><p>{loadError ?? "This video no longer exists."}</p><Link href="/library" className="button button-secondary">Back to library</Link></div>;

  const retry = async () => {
    setIsRetrying(true);
    setRetryError(null);
    try {
      const job = await api.retryJob(videoId);
      setVideo((current) => current ? { ...current, status: "queued", error_message: null, retry_count: job.retry_count ?? current.retry_count, chunk_count: 0 } : current);
      window.dispatchEvent(new Event("videoqa:videos-changed"));
    } catch (reason) {
      setRetryError(reason instanceof Error ? reason.message : "Unable to retry indexing.");
    } finally {
      setIsRetrying(false);
    }
  };

  return <div className="video-workspace">
    <div className="workspace-titlebar"><Link href="/library" className="back-link"><ArrowLeft size={18} /> Library</Link><div><p className="eyebrow">Video conversation</p><h1>{video.title}</h1></div><button type="button" className="button button-ghost button-small" onClick={newChat}><RotateCcw size={15} /> New chat</button></div>
    <div className="workspace-grid">
      <section className="player-column">
        <VideoPlayer video={video} localRef={videoRef} youtubeRef={youtubeRef} onTime={setCurrentTime} />
        <div className="video-details-panel"><div><p className="eyebrow">Video details</p><h2>{video.title}</h2><p>{video.description || (chatReady ? "This video is ready for grounded questions from its indexed transcript." : "The source video stays available while indexing runs.")}</p></div><dl><div><dt>Duration</dt><dd>{formatDuration(video.duration_seconds)}</dd></div><div><dt>Source</dt><dd>{video.source_type === "file_upload" ? "Local upload" : video.source_type === "youtube" ? "YouTube" : "Video URL"}</dd></div><div><dt>Transcript</dt><dd>{transcript.length} segments</dd></div></dl></div>
        {video.status === "failed" && <div className="workspace-notice error-state" role="alert"><strong>Indexing failed</strong><p>{video.error_message || "The transcript could not be indexed."}</p>{retryError && <p>{retryError}</p>}{video.media_available && (video.retry_count ?? 0) < 3 && <button type="button" className="button button-secondary button-small" onClick={() => void retry()} disabled={isRetrying}><RotateCcw size={14} /> {isRetrying ? "Retrying…" : "Retry indexing"}</button>}</div>}
        {(video.status === "queued" || video.status === "downloading" || video.status === "transcribing" || video.status === "chunking" || video.status === "embedding") && <div className="workspace-notice" role="status"><strong>Video is playable while indexing</strong><p>Transcript indexing is {video.status}. Chat will be enabled when transcript chunks are ready.</p></div>}
        {video.source_type === "file_upload" && !video.media_available && <div className="workspace-notice error-state" role="status"><strong>Source file missing</strong><p>This video record is still in your library, but its stored media file is unavailable.</p></div>}
        <section className="transcript-panel">
          <button type="button" className="transcript-toggle" onClick={() => setTranscriptOpen((open) => !open)} aria-expanded={transcriptOpen}><span><Subtitles size={18} /> Transcript</span>{transcriptOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</button>
          {transcriptOpen && <VirtualTranscript segments={transcript} currentTime={currentTime} highlight={highlight} onSeek={seek} />}
        </section>
      </section>
      <section className="chat-column" aria-label="Video chat">
        <div className="chat-heading"><div><p className="eyebrow">Grounded chat</p><h2>Ask about this video</h2></div>{sessionId && <span className="session-pill"><Clock3 size={14} /> Saved</span>}</div>
        <div className="message-list">
          {messages.length === 0 && <ChatEmpty ready={chatReady} status={video.status} />}
          {messages.map((message) => <ChatBubble key={String(message.id)} message={message} onSeek={seek} />)}
          <div ref={bottomRef} />
        </div>
        <form className="chat-composer" onSubmit={send}>
          <textarea
            data-testid="video-question-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending || !chatReady}
            placeholder={
              chatReady
                ? "Ask anything about this video…"
                : video.status === "failed"
                ? "Chat is unavailable until indexing succeeds"
                : isIndexing
                ? `Chat unlocks after indexing completes (${video.status})`
                : "Chat unlocks after indexing is complete"
            }
            aria-label="Question about this video"
            rows={2}
          />
          {isSending ? (
            <button type="button" className="button button-secondary composer-button" onClick={() => controllerRef.current?.abort()}>
              <PauseCircle size={18} /> Stop
            </button>
          ) : (
            <button
              data-testid="video-question-send"
              type="submit"
              className="button button-primary composer-button"
              disabled={!input.trim() || !chatReady}
              aria-label="Send question"
            >
              <Send size={18} /><span>Send</span>
            </button>
          )}
          <p>
            {chatReady
              ? "Enter to send · Shift + Enter for a new line"
              : video.status === "failed"
              ? "Retry indexing to enable grounded chat."
              : isIndexing
              ? `Transcript indexing is currently ${video.status}. Playback is available while indexing finishes.`
              : "Video playback remains available while transcript indexing completes."}
          </p>
        </form>
      </section>
    </div>
  </div>;
}

function VideoPlayer({ video, localRef, youtubeRef, onTime }: { video: VideoRecord; localRef: RefObject<HTMLVideoElement | null>; youtubeRef: RefObject<HTMLIFrameElement | null>; onTime: (seconds: number) => void }) {
  const [playbackError, setPlaybackError] = useState(false);
  if (video.source_type === "youtube") return <div className="video-player"><iframe ref={youtubeRef} src={`https://www.youtube.com/embed/${encodeURIComponent(video.video_id)}?enablejsapi=1&playsinline=1&rel=0`} title={`YouTube player: ${video.title}`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen /></div>;
  const mediaUrl = video.media_url;
  if (!video.media_available || !mediaUrl) return <div className="video-player unavailable-player"><VideoOff size={34} /><h2>Source file missing</h2><p>The video record is still in your library, but the media file is unavailable in configured storage.</p></div>;
  if (playbackError) return <div className="video-player unavailable-player"><VideoOff size={34} /><h2>Playback unavailable</h2><p>The stored file could not be decoded by this browser.</p></div>;
  return <div className="video-player"><video ref={localRef} src={mediaUrl} controls preload="metadata" onTimeUpdate={(event) => onTime(event.currentTarget.currentTime)} onLoadedMetadata={(event) => onTime(event.currentTarget.currentTime)} onError={() => setPlaybackError(true)} /></div>;
}

function ChatEmpty({ ready, status }: { ready: boolean; status: string }) { return <div className="chat-empty"><span><Sparkles size={24} /></span><h3>{ready ? "Start a grounded conversation" : status === "failed" ? "Chat is unavailable" : "Chat will be ready soon"}</h3><p>{ready ? "Ask a question in your own words. Evidence and timestamp citations will appear with the answer." : status === "failed" ? "Retry indexing after checking the stored error message." : "You can watch the video while its transcript is being indexed."}</p></div>; }

function ChatBubble({ message, onSeek }: { message: ChatMessage; onSeek: (seconds: number) => void }) {
  return <article className={`chat-message ${message.role} ${message.error ? "message-error" : ""}`}><div className="message-role">{message.role === "user" ? "You" : "VideoQA"}</div><div className="message-content"><ReactMarkdown>{message.content || " "}</ReactMarkdown>{message.isStreaming && <span className="typing-cursor" aria-label="Generating answer" />}{message.citations && message.citations.length > 0 && <div className="citation-list" aria-label="Verified video citations">{message.citations.map((citation, index) => <CitationButton key={`${citation.chunk_id ?? index}-${citation.start_seconds}`} citation={citation} onSeek={onSeek} />)}</div>}</div></article>;
}

function CitationButton({ citation, onSeek }: { citation: Citation; onSeek: (seconds: number) => void }) {
  return <button type="button" className="citation-button" onClick={() => onSeek(citation.start_seconds)} title={citation.text_snippet}><Clock3 size={14} /><span>{citation.start_display}–{citation.end_display}</span><small>{citation.title || "Video evidence"}</small></button>;
}

function VirtualTranscript({ segments, currentTime, highlight, onSeek }: { segments: TranscriptSegment[]; currentTime: number; highlight: number | null; onSeek: (seconds: number) => void }) {
  const rowHeight = 68;
  const [scrollTop, setScrollTop] = useState(0);
  const visibleCount = 6;
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - 4);
  const end = Math.min(segments.length, start + visibleCount + 8);
  const visible = useMemo(() => segments.slice(start, end), [end, segments, start]);
  return <div className="transcript-scroll" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}><div style={{ height: segments.length * rowHeight, position: "relative" }}>{visible.map((segment, index) => {
    const active = currentTime >= segment.start_seconds && currentTime < segment.end_seconds || highlight === segment.start_seconds;
    return <button type="button" key={segment.segment_index} className={`transcript-row ${active ? "active" : ""}`} style={{ transform: `translateY(${(start + index) * rowHeight}px)` }} onClick={() => onSeek(segment.start_seconds)}><time>{formatDuration(segment.start_seconds)}</time><span>{segment.text_english || segment.text_original || "Transcript segment"}</span></button>;
  })}</div></div>;
}

function WorkspaceSkeleton() { return <div className="workspace-skeleton"><div className="skeleton skeleton-line short" /><div className="workspace-grid"><div className="skeleton player-skeleton" /><div className="skeleton chat-skeleton" /></div></div>; }
