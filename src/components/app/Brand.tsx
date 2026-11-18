import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-[14px] bg-gradient-warm text-primary-foreground shadow-glow",
        className,
      )}
      aria-hidden
    >
      <span className="font-han text-[19px] font-bold leading-none">枫</span>
      <span className="absolute inset-0 rounded-[14px] ring-1 ring-inset ring-white/15" />
    </span>
  );
}

export function BrandLockup({ subtitle = "Creator loop" }: { subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      <div className="leading-tight">
        <p className="font-display text-[17px] font-semibold tracking-tight text-foreground">Feng Hotpot</p>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}
