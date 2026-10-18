"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { VideoWorkspace } from "@/components/video-workspace";

export default function VideoPage() {
  return <Suspense fallback={<div className="workspace-skeleton" aria-busy="true" />}><VideoPageContent /></Suspense>;
}

function VideoPageContent() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  return <VideoWorkspace videoId={params.id} initialSessionId={search.get("session")} />;
}
