"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadEvent, replayEvent, type RelayEvent } from "../lib/api";

const statusClass = (status: string) => {
  if (status === "succeeded") return "bg-lime-100 text-lime-900";
  if (status === "dead") return "bg-rose-100 text-rose-900";
  if (status === "failed") return "bg-amber-100 text-amber-950";
  return "bg-stone-200 text-stone-700";
};

export function EventDetail({ id }: { id: string }) {
  const [event, setEvent] = useState<RelayEvent | null>(null);
  const [error, setError] = useState("");
  const [replaying, setReplaying] = useState(false);

  const refresh = async () => {
    setEvent(await loadEvent(id));
  };

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const next = await loadEvent(id);
        if (!stopped) {
          setEvent(next);
          setError("");
        }
      } catch (caught) {
        if (!stopped) setError(caught instanceof Error ? caught.message : "Event not found.");
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [id]);

  const handleReplay = async () => {
    setReplaying(true);
    try {
      await replayEvent(id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Replay failed.");
    } finally {
      setReplaying(false);
    }
  };

  if (!event) {
    return <main className="mx-auto max-w-5xl px-5 py-8 text-sm text-stone-600">{error || "Loading event."}</main>;
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <Link href="/" className="text-sm text-orange-800">
        Back to the console
      </Link>
      <header className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-stone-500">{event.correlation_id}</p>
          <h1 className="mt-1 text-2xl font-medium">
            {event.provider} · {event.type}
          </h1>
          <p className="mt-1 font-mono text-sm text-stone-600">{event.external_id}</p>
        </div>
        <button
          type="button"
          onClick={() => void handleReplay()}
          disabled={replaying}
          className="rounded-md bg-orange-700 px-4 py-2 text-sm text-white disabled:opacity-60"
        >
          {replaying ? "Replaying" : "Replay from Postgres"}
        </button>
      </header>
      {error ? <p className="mt-4 rounded-md bg-rose-100 px-3 py-2 text-sm text-rose-900">{error}</p> : null}

      <section className="mt-6 overflow-hidden rounded-lg border border-stone-300 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3 font-medium">Consumer</th>
              <th className="px-4 py-3 font-medium">Attempt</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Error</th>
            </tr>
          </thead>
          <tbody>
            {event.deliveries.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-stone-500">
                  Waiting for a worker.
                </td>
              </tr>
            ) : (
              event.deliveries.map((row, index) => (
                <tr key={`${row.consumer}-${row.attempt}-${index}`} className="border-t border-stone-100">
                  <td className="px-4 py-3 font-mono text-xs">{row.consumer}</td>
                  <td className="px-4 py-3 font-mono">{row.attempt}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-2 py-0.5 font-mono text-xs ${statusClass(row.status)}`}>{row.status}</span>
                  </td>
                  <td className="px-4 py-3 text-stone-600">{row.error ?? ""}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <pre className="overflow-auto rounded-lg border border-stone-300 bg-white p-4 font-mono text-xs">
          {JSON.stringify(event.raw, null, 2)}
        </pre>
        <pre className="overflow-auto rounded-lg border border-stone-300 bg-white p-4 font-mono text-xs">
          {JSON.stringify(event.canonical, null, 2)}
        </pre>
      </section>
    </main>
  );
}
