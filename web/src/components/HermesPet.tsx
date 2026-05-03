import hermesPetUrl from "@/assets/hermes-pet.svg";
import { useHermesPets } from "@/hooks/useHermesPets";
import { cn } from "@/lib/utils";
import type { PetInstance, PetState } from "@/lib/petEvents";

const STATE_LABEL: Record<PetState, string> = {
  idle: "idle",
  running: "running",
  waiting: "waiting",
  failed: "failed",
  review: "review",
};

const STATE_TONE: Record<PetState, string> = {
  idle: "bg-midground/40",
  running: "bg-success",
  waiting: "bg-warning",
  failed: "bg-destructive",
  review: "bg-[#20c7ad]",
};

interface HermesPetProps {
  pet: PetInstance;
  compact?: boolean;
}

export function HermesPet({ pet, compact = false }: HermesPetProps) {
  return (
    <figure
      className={cn(
        "hermes-pet pointer-events-auto flex shrink-0 flex-col items-center gap-1.5",
        compact ? "w-[92px]" : "w-[118px]",
      )}
      data-source={pet.source}
      data-state={pet.state}
      title={`${pet.label}: ${pet.message}`}
    >
      <figcaption
        className={cn(
          "max-w-full overflow-hidden rounded border border-current/15",
          "bg-background-base/90 px-2 py-1 text-center shadow-lg backdrop-blur-sm",
          "normal-case tracking-normal text-midground",
          compact ? "text-[0.58rem] leading-[0.72rem]" : "text-[0.65rem] leading-3",
        )}
      >
        <span className="block truncate font-medium">{pet.label}</span>
        <span className="mt-0.5 flex min-w-0 items-center justify-center gap-1 opacity-75">
          <span
            className={cn("h-1.5 w-1.5 shrink-0 rounded-full", STATE_TONE[pet.state])}
            aria-hidden="true"
          />
          <span className="truncate">{pet.message || STATE_LABEL[pet.state]}</span>
        </span>
      </figcaption>

      <div
        className={cn(
          "hermes-pet-pad relative grid place-items-center",
          compact ? "h-[86px] w-[86px]" : "h-[108px] w-[108px]",
        )}
      >
        <img
          src={hermesPetUrl}
          alt=""
          aria-hidden="true"
          className="hermes-pet-visual h-full w-full select-none object-contain"
          data-state={pet.state}
          draggable={false}
        />
      </div>
    </figure>
  );
}

interface HermesPetDockProps {
  channel?: string;
  className?: string;
  includeRelay?: boolean;
  mode?: "overlay" | "panel";
  showIdleLocal?: boolean;
}

export function HermesPetDock({
  channel,
  className,
  includeRelay = true,
  mode = "overlay",
  showIdleLocal = true,
}: HermesPetDockProps) {
  const pets = useHermesPets({ channel, includeRelay, showIdleLocal });

  if (pets.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "hermes-pet-dock flex min-w-0 items-end gap-2",
        mode === "overlay"
          ? "pointer-events-none fixed bottom-3 left-1/2 z-[35] -translate-x-1/2"
          : "relative flex-wrap",
        className,
      )}
      data-mode={mode}
    >
      {pets.map((pet) => (
        <HermesPet compact={mode === "overlay"} key={pet.id} pet={pet} />
      ))}
    </div>
  );
}
