"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

const TERMINAL = new Set(["ready", "failed", "cancelled"]);

export function useJobStatus(jobId: string | null, onTerminal?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await api.job(jobId);
        if (!alive) return;
        setJob(next);
        setError(null);
        if (TERMINAL.has(next.status)) onTerminal?.(next);
        else timer = setTimeout(poll, 1800);
      } catch (reason) {
        if (!alive) return;
        setError(reason instanceof Error ? reason.message : "Unable to check processing status.");
        timer = setTimeout(poll, 4000);
      }
    };
    void poll();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, onTerminal]);

  return { job, error };
}
