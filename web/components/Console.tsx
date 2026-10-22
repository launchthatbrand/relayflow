"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  loadConsumers,
  loadEvents,
  loadStats,
  samples,
  sendSample,
  setFailSwitch,
  type ConsumerSwitch,
  type RelayEvent,
  type Stats,
} from "../lib/api";

const emptyStats: Stats = { ingested: 0, duplicates: 0, delivered: 0, dead: 0, queues: {} };

const statusClass = (status: string) => {
  if (status === "succeeded") return "bg-lime-100 text-lime-900";
  if (status === "dead") return "bg-rose-100 text-rose-900";
  if (status === "failed") return "bg-amber-100 text-amber-950";
  return "bg-stone-200 text-stone-700";
};

export function Console() {
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [events, setEvents] = useState<RelayEvent[]>([]);
  const [consumers, setConsumers] = useState<ConsumerSwitch[]>([]);
  const [provider, setProvider] = useState<string>(samples[0].provider);
  const [payload, setPayload] = useState(JSON.stringify(samples[0].payload, null, 2));
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  const refresh = async () => {
    const [nextStats, nextEvents, nextConsumers] = await Promise.all([
      loadStats(),
      loadEvents(),
      loadConsumers(),
    ]);
    setStats(nextStats);
    setEvents(nextEvents.events);
    setConsumers(nextConsumers.consumers);
  };

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        await refresh();
        if (!stopped) setError("");
      } catch (caught) {
        if (!stopped) setError(caught instanceof Error ? caught.message : "The console could not reach the API.");
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  const handleSample = (index: number) => {
    const sample = samples[index];
    setProvider(sample.provider);
    setPayload(JSON.stringify(sample.payload, null, 2));
  };

  const handleSend = async () => {
    setSending(true);
    try {
      await sendSample(provider, JSON.parse(payload) as unknown);
      await refresh();
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Send failed.");
    } finally {
      setSending(false);
    }
  };

  const handleFail = async (name: string, failNext: boolean) => {
    await setFailSwitch(name, failNext);
    await refresh();
  };

  return (
    <main className="mx-auto max-w-6xl px-5 py-8">
      <header className="flex items-end justify-between gap-4 border-b border-stone-300 pb-5">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-stone-500">Operator console</p>
          <h1 className="mt-1 text-3xl font-medium tracking-tight">RelayFlow</h1>
        </div>
        <p className="max-w-sm text-right text-sm text-stone-600">
          One signed webhook is published to a topic exchange. CRM, email, and audit each take the copy their binding matches.
        </p>
      </header>

      {error ? <p className="mt-4 rounded-md bg-rose-100 px-3 py-2 text-sm text-rose-900">{error}</p> : null}

      <section className="mt-6 grid gap-3 sm:grid-cols-4">
        {[
          ["Ingested", stats.ingested],
          ["Duplicates", stats.duplicates],
          ["Delivered", stats.delivered],
          ["Dead-lettered", stats.dead],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-stone-300 bg-white px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-stone-500">{label}</p>
            <p className="mt-1 font-mono text-2xl">{value}</p>
          </div>
        ))}
      </section>

      <section className="mt-3 flex flex-wrap gap-2">
        {Object.entries(stats.queues).map(([name, depth]) => (
          <span key={name} className="rounded-full border border-stone-300 bg-white px-3 py-1 font-mono text-xs">
            {name} {depth}
          </span>
        ))}
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-lg border border-stone-300 bg-white p-4">
          <h2 className="text-sm font-medium">Send a sample webhook</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {samples.map((sample, index) => (
              <button
                key={sample.label}
                type="button"
                onClick={() => handleSample(index)}
                className="rounded-full border border-stone-300 px-3 py-1 text-sm hover:border-orange-700"
              >
                {sample.label}
              </button>
            ))}
          </div>
          <label className="mt-4 block text-xs uppercase tracking-wide text-stone-500" htmlFor="provider">
            Provider
          </label>
          <select
            id="provider"
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            className="mt-1 w-full rounded-md border border-stone-300 bg-stone-50 px-3 py-2"
          >
            <option value="stripe">stripe</option>
            <option value="monday">monday</option>
            <option value="email">email</option>
          </select>
          <label className="mt-3 block text-xs uppercase tracking-wide text-stone-500" htmlFor="payload">
            Payload
          </label>
          <textarea
            id="payload"
            value={payload}
            onChange={(event) => setPayload(event.target.value)}
            rows={8}
            className="mt-1 w-full rounded-md border border-stone-300 bg-stone-50 p-3 font-mono text-sm"
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={sending}
            className="mt-3 rounded-md bg-orange-700 px-4 py-2 text-sm text-white disabled:opacity-60"
          >
            {sending ? "Sending" : "Send signed webhook"}
          </button>
        </div>

        <div className="rounded-lg border border-stone-300 bg-white p-4">
          <h2 className="text-sm font-medium">Fail a consumer</h2>
          <p className="mt-1 text-sm text-stone-600">
            Leave this on and the next deliveries for that queue retry twice, then land on the dead-letter exchange.
          </p>
          <ul className="mt-4 space-y-3">
            {consumers.map((consumer) => (
              <li key={consumer.name} className="flex items-center justify-between gap-3">
                <span className="font-mono text-sm">{consumer.name}</span>
                <button
                  type="button"
                  aria-pressed={consumer.fail_next}
                  onClick={() => void handleFail(consumer.name, !consumer.fail_next)}
                  className={
                    consumer.fail_next
                      ? "rounded-full bg-rose-700 px-3 py-1 text-sm text-white"
                      : "rounded-full border border-stone-300 px-3 py-1 text-sm"
                  }
                >
                  {consumer.fail_next ? "Failing" : "Healthy"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mt-6 overflow-hidden rounded-lg border border-stone-300 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3 font-medium">When</th>
              <th className="px-4 py-3 font-medium">Provider</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">External id</th>
              <th className="px-4 py-3 font-medium">Consumers</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-stone-500">
                  No events yet.
                </td>
              </tr>
            ) : (
              events.map((event) => (
                <tr key={event.id} className="border-t border-stone-100">
                  <td className="px-4 py-3 font-mono text-xs">{new Date(event.received_at).toLocaleTimeString()}</td>
                  <td className="px-4 py-3">{event.provider}</td>
                  <td className="px-4 py-3 font-mono text-xs">{event.type}</td>
                  <td className="px-4 py-3 font-mono text-xs">{event.external_id}</td>
                  <td className="px-4 py-3">
                    <Link href={`/events/${event.id}`} className="inline-flex flex-wrap gap-1">
                      {Object.values(event.consumers).length === 0 ? (
                        <span className="text-stone-500">queued</span>
                      ) : (
                        Object.values(event.consumers).map((item) => (
                          <span key={item.consumer} className={`rounded px-2 py-0.5 font-mono text-xs ${statusClass(item.status)}`}>
                            {item.consumer} {item.status}
                          </span>
                        ))
                      )}
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
