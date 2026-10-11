"use client";

import { useParams, useSearchParams } from "next/navigation";
import { VideoWorkspace } from "@/components/video-workspace";

export default function VideoPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  return <VideoWorkspace videoId={params.id} initialSessionId={search.get("session")} />;
}
