"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LibraryView } from "@/components/library-view";

export default function LibraryPage() {
  return <Suspense fallback={<div className="page-content" aria-busy="true">Loading library…</div>}><LibraryContent /></Suspense>;
}

function LibraryContent() {
  const search = useSearchParams();
  return <LibraryView initialQuery={search.get("q") ?? ""} />;
}
