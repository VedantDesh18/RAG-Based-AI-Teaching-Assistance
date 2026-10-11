"use client";

import { useSearchParams } from "next/navigation";
import { LibraryView } from "@/components/library-view";

export default function LibraryPage() {
  const search = useSearchParams();
  return <LibraryView initialQuery={search.get("q") ?? ""} />;
}
