"use client";

import { useCallback, useRef, useState } from "react";
import { api, ApiError, uploadVideo } from "@/lib/api";
import type { JobStart } from "@/lib/types";

export type IngestionState = {
  job: JobStart | null;
  upload: { loaded: number; total: number } | null;
  error: string | null;
  source: "url" | "file" | null;
};

export function useIngestion(onStart?: (job: JobStart) => void) {
  const [state, setState] = useState<IngestionState>({ job: null, upload: null, error: null, source: null });
  const cancelUpload = useRef<null | (() => void)>(null);

  const startUrl = useCallback(async (url: string) => {
    setState({ job: null, upload: null, error: null, source: "url" });
    try {
      const job = await api.ingestUrl(url);
      setState({ job, upload: null, error: null, source: "url" });
      onStart?.(job);
      return job;
    } catch (reason) {
      const message = reason instanceof ApiError ? reason.message : "Unable to import this video.";
      setState({ job: null, upload: null, error: message, source: "url" });
      throw reason;
    }
  }, [onStart]);

  const startFile = useCallback(async (file: File) => {
    setState({ job: null, upload: { loaded: 0, total: file.size }, error: null, source: "file" });
    const request = uploadVideo(file, (loaded, total) => setState((current) => ({ ...current, upload: { loaded, total } })));
    cancelUpload.current = request.cancel;
    try {
      const job = await request.promise;
      setState({ job, upload: null, error: null, source: "file" });
      onStart?.(job);
      return job;
    } catch (reason) {
      const message = reason instanceof ApiError ? reason.message : "Upload failed.";
      setState((current) => ({ ...current, upload: null, error: message }));
      throw reason;
    } finally {
      cancelUpload.current = null;
    }
  }, [onStart]);

  const cancel = () => {
    cancelUpload.current?.();
  };

  return { ...state, startUrl, startFile, cancel };
}
