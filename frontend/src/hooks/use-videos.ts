"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { VideoRecord } from "@/lib/types";

export function useVideos() {
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setVideos(await api.videos());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to load your library.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener("videoqa:videos-changed", refresh);
    return () => window.removeEventListener("videoqa:videos-changed", refresh);
  }, [refresh]);

  const remove = async (videoId: string) => {
    await api.removeVideo(videoId);
    setVideos((current) => current.filter((video) => video.video_id !== videoId));
  };

  return { videos, setVideos, isLoading, error, refresh, remove };
}
