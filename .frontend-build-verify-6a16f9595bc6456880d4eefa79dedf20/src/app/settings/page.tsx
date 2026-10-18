"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, Moon, Sun, MonitorCog } from "lucide-react";
import { api } from "@/lib/api";
import { useTheme, type ThemePreference } from "@/hooks/use-theme";
import type { Health } from "@/lib/types";

const choices: Array<{ value: ThemePreference; label: string; icon: typeof Sun; copy: string }> = [
  { value: "light", label: "Light", icon: Sun, copy: "Soft backgrounds and crisp contrast." },
  { value: "dark", label: "Dark", icon: Moon, copy: "A focused deep-slate workspace." },
  { value: "system", label: "System", icon: MonitorCog, copy: "Follow this device’s setting." },
];

export default function SettingsPage() {
  const { preference, setPreference } = useTheme();
  const [health, setHealth] = useState<"loading" | "ok" | "error">("loading");
  const [healthDetails, setHealthDetails] = useState<Health | null>(null);
  useEffect(() => { api.health().then((result) => { setHealthDetails(result); setHealth(result.services?.api === "ok" ? "ok" : "error"); }).catch(() => setHealth("error")); }, []);
  return <div className="page-stack settings-page">
    <section className="page-intro"><p className="eyebrow">Workspace preferences</p><h1>Settings</h1><p>Adjust the local workspace experience without exposing unsafe server configuration in the browser.</p></section>
    <section className="settings-section"><div><h2>Appearance</h2><p>Your preference is stored locally and restored after refresh.</p></div><div className="theme-choice-grid">{choices.map(({ value, label, icon: Icon, copy }) => <button type="button" key={value} onClick={() => setPreference(value)} className={`theme-choice ${preference === value ? "selected" : ""}`} aria-pressed={preference === value}><Icon size={19} /><strong>{label}</strong><span>{copy}</span></button>)}</div></section>
    <section className="settings-section"><div><h2>Retrieval & models</h2><p>Models and retrieval settings are configured by the local backend. Their values remain server-side so they cannot be altered accidentally from the browser.</p></div><div className="settings-readonly"><p><strong>Embedding model</strong><span>Configured by backend</span></p><p><strong>Generation model</strong><span>Configured by backend</span></p><p><strong>Similarity threshold</strong><span>Configured by backend</span></p></div></section>
    <section className="settings-section"><div><h2>Service health</h2><p>Checks the VideoQA API and local Ollama service without exposing server controls in the browser.</p></div><div className={`health-card ${health === "ok" ? "healthy" : health === "error" ? "unhealthy" : ""}`}>{health === "loading" ? <span className="spinner-small" /> : health === "ok" ? <CheckCircle2 size={20} /> : <CircleAlert size={20} />}<div><strong>{health === "loading" ? "Checking backend…" : health === "ok" ? "VideoQA backend connected" : "Backend unavailable"}</strong><span>{health === "ok" ? `Ollama: ${healthDetails?.services?.ollama === "ok" ? "connected" : "unavailable"}.` : "Start the FastAPI service, then refresh this page."}</span></div></div></section>
  </div>;
}
