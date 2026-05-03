import { useEffect, useState } from "react";

import {
  localPetPatchFromEvent,
  parseHermesEventFrame,
  relayPetFromFrame,
  type PetInstance,
} from "@/lib/petEvents";

interface UseHermesPetsOptions {
  channel?: string;
  includeRelay?: boolean;
  showIdleLocal?: boolean;
}

const LOCAL_PET_ID = "local:hermes";
const RECONNECT_MS = 2_500;

function idleLocalPet(source: PetInstance["source"] = "local"): PetInstance {
  return {
    id: LOCAL_PET_ID,
    label: source === "demo" ? "Hermes Preview" : "Hermes Local",
    source,
    state: "idle",
    message: "ready",
    updatedAt: Date.now(),
  };
}

function upsertPet(pets: PetInstance[], next: PetInstance): PetInstance[] {
  const index = pets.findIndex((pet) => pet.id === next.id);
  if (index === -1) {
    return [...pets, next];
  }

  const copy = [...pets];
  copy[index] = { ...copy[index], ...next };
  return copy;
}

export function useHermesPets({
  channel,
  includeRelay = true,
  showIdleLocal = true,
}: UseHermesPetsOptions = {}): PetInstance[] {
  const [pets, setPets] = useState<PetInstance[]>(() =>
    showIdleLocal ? [idleLocalPet(channel ? "local" : "demo")] : [],
  );

  useEffect(() => {
    if (!showIdleLocal) {
      return;
    }

    setPets((prev) => upsertPet(prev, idleLocalPet(channel ? "local" : "demo")));
  }, [channel, showIdleLocal]);

  useEffect(() => {
    const token = window.__HERMES_SESSION_TOKEN__;
    if (!token || !channel) {
      return;
    }

    let ws: WebSocket | null = null;
    let reconnectTimer = 0;
    let closing = false;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const qs = new URLSearchParams({ token, channel });
      ws = new WebSocket(`${proto}//${window.location.host}/api/events?${qs}`);

      ws.addEventListener("message", (ev) => {
        if (typeof ev.data !== "string") {
          return;
        }

        const event = parseHermesEventFrame(ev.data);
        if (!event) {
          return;
        }

        const patch = localPetPatchFromEvent(event);
        if (!patch) {
          return;
        }

        setPets((prev) =>
          upsertPet(prev, {
            ...idleLocalPet("local"),
            ...patch,
            updatedAt: Date.now(),
          }),
        );
      });

      ws.addEventListener("close", () => {
        if (!closing) {
          reconnectTimer = window.setTimeout(connect, RECONNECT_MS);
        }
      });
    };

    connect();

    return () => {
      closing = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
    };
  }, [channel]);

  useEffect(() => {
    const token = window.__HERMES_SESSION_TOKEN__;
    if (!token || !includeRelay) {
      return;
    }

    let ws: WebSocket | null = null;
    let reconnectTimer = 0;
    let closing = false;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const qs = new URLSearchParams({ token });
      ws = new WebSocket(
        `${proto}//${window.location.host}/api/pet/relay/events?${qs}`,
      );

      ws.addEventListener("message", (ev) => {
        if (typeof ev.data !== "string") {
          return;
        }

        let frame: unknown;
        try {
          frame = JSON.parse(ev.data);
        } catch {
          return;
        }

        const pet = relayPetFromFrame(frame);
        if (pet) {
          setPets((prev) => upsertPet(prev, pet));
        }
      });

      ws.addEventListener("close", () => {
        if (!closing) {
          reconnectTimer = window.setTimeout(connect, RECONNECT_MS);
        }
      });
    };

    connect();

    return () => {
      closing = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
    };
  }, [includeRelay]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const now = Date.now();
      setPets((prev) =>
        prev.map((pet) => {
          if (!pet.expiresAt || pet.expiresAt > now) {
            return pet;
          }

          return {
            ...pet,
            state: "idle",
            message: pet.source === "relay" ? "remote ready" : "ready",
            updatedAt: now,
            expiresAt: undefined,
          };
        }),
      );
    }, 1_000);

    return () => window.clearInterval(interval);
  }, []);

  return pets;
}
