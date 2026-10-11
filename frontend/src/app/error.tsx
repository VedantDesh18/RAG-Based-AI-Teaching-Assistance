"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="route-error"><h1>Something interrupted this view.</h1><p>Your indexed videos are safe. Try loading this screen again.</p><button type="button" className="button button-primary" onClick={reset}>Try again</button></div>;
}
