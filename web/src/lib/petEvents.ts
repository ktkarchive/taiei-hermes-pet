export const PET_STATES = ["idle", "running", "waiting", "failed", "review"] as const;

export type PetState = (typeof PET_STATES)[number];
export type PetSource = "local" | "relay" | "demo";

export interface PetInstance {
  id: string;
  label: string;
  source: PetSource;
  state: PetState;
  message: string;
  updatedAt: number;
  expiresAt?: number;
}

export interface HermesEvent {
  type: string;
  payload?: unknown;
}

export type PetPatch = Pick<PetInstance, "state" | "message"> & {
  expiresAt?: number;
};

const PET_STATE_SET: ReadonlySet<string> = new Set(PET_STATES);

const RUNNING_TYPES = new Set([
  "message.start",
  "message.delta",
  "thinking.delta",
  "reasoning.delta",
  "tool.start",
  "tool.progress",
  "tool.generating",
  "subagent.start",
  "subagent.progress",
  "subagent.tool.start",
  "subagent.tool.progress",
]);

const WAITING_TYPES = new Set([
  "approval.request",
  "clarify.request",
  "secret.request",
  "sudo.request",
  "subagent.spawn_requested",
]);

const FAILED_TYPES = new Set([
  "error",
  "message.error",
  "tool.error",
  "subagent.error",
]);

const REVIEW_TYPES = new Set([
  "message.complete",
  "turn.complete",
  "review.start",
  "review.ready",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asPetState(value: unknown): PetState | null {
  if (typeof value !== "string") return null;
  const clean = value.trim().toLowerCase();
  return PET_STATE_SET.has(clean) ? (clean as PetState) : null;
}

export function parseHermesEventFrame(data: string): HermesEvent | null {
  let frame: unknown;

  try {
    frame = JSON.parse(data);
  } catch {
    return null;
  }

  const envelope = asRecord(frame);
  if (envelope?.method !== "event") {
    return null;
  }

  const params = asRecord(envelope.params);
  const type = readString(params?.type);
  if (!type) {
    return null;
  }

  return { type, payload: params?.payload };
}

function payloadLabel(payload: unknown): string | null {
  const p = asRecord(payload);
  return (
    readString(p?.name) ??
    readString(p?.tool) ??
    readString(p?.context) ??
    readString(p?.summary) ??
    readString(p?.preview) ??
    readString(p?.message) ??
    readString(p?.error)
  );
}

export function localPetPatchFromEvent(event: HermesEvent): PetPatch | null {
  const label = payloadLabel(event.payload);
  const payload = asRecord(event.payload);

  if (event.type === "tool.complete") {
    return payload?.error
      ? { state: "failed", message: label ?? "tool failed", expiresAt: Date.now() + 8_000 }
      : { state: "review", message: label ?? "tool complete", expiresAt: Date.now() + 5_000 };
  }

  if (RUNNING_TYPES.has(event.type)) {
    return {
      state: "running",
      message: label ?? "working",
      expiresAt: Date.now() + 12_000,
    };
  }

  if (WAITING_TYPES.has(event.type)) {
    return {
      state: "waiting",
      message: label ?? "waiting for input",
      expiresAt: Date.now() + 60_000,
    };
  }

  if (FAILED_TYPES.has(event.type)) {
    return {
      state: "failed",
      message: label ?? "attention needed",
      expiresAt: Date.now() + 12_000,
    };
  }

  if (REVIEW_TYPES.has(event.type)) {
    const status = readString(payload?.status);
    if (status === "error" || status === "failed") {
      return {
        state: "failed",
        message: label ?? "run failed",
        expiresAt: Date.now() + 12_000,
      };
    }
    return {
      state: "review",
      message: label ?? "ready to review",
      expiresAt: Date.now() + 5_000,
    };
  }

  return null;
}

export function relayPetFromFrame(frame: unknown, now = Date.now()): PetInstance | null {
  const envelope = asRecord(frame);
  if (envelope?.type !== "pet.relay") {
    return null;
  }

  const payload = asRecord(envelope.payload);
  if (!payload) {
    return null;
  }

  const sourceId = readString(payload.source_id) ?? "remote";
  const state = asPetState(payload.state) ?? "idle";
  const ttlMs = readNumber(payload.ttl_ms);
  const updatedAt = readNumber(payload.updated_at) ?? now;

  return {
    id: `relay:${sourceId}`,
    label: readString(payload.label) ?? sourceId,
    source: "relay",
    state,
    message: readString(payload.message) ?? readString(payload.event_type) ?? state,
    updatedAt,
    expiresAt: ttlMs ? now + ttlMs : undefined,
  };
}
