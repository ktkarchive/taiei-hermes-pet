import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Radio, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Badge } from "@nous-research/ui/ui/components/badge";

import { HermesPetDock } from "@/components/HermesPet";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type PetRelayStatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const SAMPLE_EVENT = `curl -X POST http://127.0.0.1:9119/api/pet/relay/events \\
  -H "Content-Type: application/json" \\
  -H "X-Hermes-Pet-Relay-Token: $HERMES_PET_RELAY_TOKEN" \\
  -d '{"source_id":"office-hermes","label":"Office Hermes","state":"running","message":"tool call","ttl_ms":12000}'`;

export default function PetsPage() {
  const [status, setStatus] = useState<PetRelayStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      setStatus(await api.getPetRelayStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load relay status");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <main className="normal-case mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4">
      <section className="grid min-h-[260px] gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Card className="flex min-h-[260px] flex-col">
          <CardHeader className="flex-row items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4" />
              Hermes pets
            </CardTitle>
            <Badge tone={status?.relay_enabled ? "success" : "secondary"}>
              {status?.relay_enabled ? "relay on" : "local"}
            </Badge>
          </CardHeader>
          <CardContent className="flex flex-1 items-end justify-center pb-6">
            <HermesPetDock includeRelay mode="panel" showIdleLocal />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Radio className="h-4 w-4" />
              Online relay
            </CardTitle>
            <Button
              ghost
              size="sm"
              onClick={refresh}
              disabled={refreshing}
              prefix={<RefreshCw className={cn(refreshing && "animate-spin")} />}
            >
              refresh
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-2 sm:grid-cols-2">
              <StatusCell label="token env" value={status?.token_env ?? "HERMES_PET_RELAY_TOKEN"} />
              <StatusCell label="subscribers" value={String(status?.subscriber_count ?? 0)} />
              <StatusCell label="header" value={status?.token_header ?? "X-Hermes-Pet-Relay-Token"} />
              <StatusCell label="states" value={status?.states.join(", ") ?? "idle, running, waiting, failed, review"} />
            </div>

            <div className="rounded border border-current/15 bg-background-base/60 p-3">
              <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" />
                remote pulse
              </div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-black/35 p-3 font-mono-ui text-[0.68rem] leading-4 text-midground/90">
                {SAMPLE_EVENT}
              </pre>
            </div>

            {error && (
              <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

function StatusCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-current/15 bg-background-base/50 px-3 py-2">
      <div className="text-[0.62rem] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="truncate font-mono-ui text-xs text-midground" title={value}>
        {value}
      </div>
    </div>
  );
}
