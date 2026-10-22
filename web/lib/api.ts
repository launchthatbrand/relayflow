export type ConsumerState = {
  consumer: string;
  attempt: number;
  status: string;
  error: string | null;
  created_at: string;
};

export type RelayEvent = {
  id: string;
  provider: string;
  type: string;
  external_id: string;
  correlation_id: string;
  received_at: string;
  raw: Record<string, unknown>;
  canonical: Record<string, unknown>;
  consumers: Record<string, ConsumerState>;
  deliveries: ConsumerState[];
};

export type Stats = {
  ingested: number;
  duplicates: number;
  delivered: number;
  dead: number;
  queues: Record<string, number>;
};

export type ConsumerSwitch = {
  name: string;
  fail_next: boolean;
};

export const samples = [
  {
    label: "Stripe checkout",
    provider: "stripe",
    payload: { type: "checkout.completed", id: "evt_1001", account: "acme", amount: 2500 },
  },
  {
    label: "Monday item",
    provider: "monday",
    payload: { type: "item.updated", id: "item_44", account: "appropriations", board: "Bills" },
  },
  {
    label: "Email delivered",
    provider: "email",
    payload: { type: "message.completed", id: "msg_8", account: "desk", to: "clerk@example.com" },
  },
] as const;

async function read<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const loadStats = () => read<Stats>("/api/stats");
export const loadEvents = () => read<{ events: RelayEvent[] }>("/api/events");
export const loadEvent = (id: string) => read<RelayEvent>(`/api/events/${id}`);
export const loadConsumers = () => read<{ consumers: ConsumerSwitch[] }>("/api/consumers");

export const sendSample = (provider: string, payload: unknown) =>
  read<{ status: string; event_id: string }>("/api/samples", {
    method: "POST",
    body: JSON.stringify({ provider, payload }),
  });

export const setFailSwitch = (name: string, failNext: boolean) =>
  read<ConsumerSwitch>(`/api/consumers/${name}`, {
    method: "PUT",
    body: JSON.stringify({ fail_next: failNext }),
  });

export const replayEvent = (id: string) =>
  read<{ status: string }>(`/api/events/${id}/replay`, { method: "POST" });
