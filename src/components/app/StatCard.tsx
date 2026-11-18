import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "primary" | "jade" | "gold" | "neutral";
  emphasis?: boolean;
}

const tones = {
  primary: "bg-primary-soft text-primary",
  jade: "bg-accent-soft text-accent",
  gold: "bg-gold-soft text-gold",
  neutral: "bg-muted text-muted-foreground",
};

export function StatCard({ label, value, hint, icon: Icon, tone = "neutral", emphasis }: StatCardProps) {
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-lg border border-border/70 bg-card p-4 shadow-soft transition-shadow hover:shadow-elegant",
        emphasis && "border-primary/25 bg-gradient-surface",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
        {Icon ? (
          <span className={cn("flex size-7 items-center justify-center rounded-sm", tones[tone])}>
            <Icon className="size-3.5" />
          </span>
        ) : null}
      </div>
      <p className="mt-2 font-display text-[32px] leading-none tracking-tight text-foreground tabular">{value}</p>
      {hint ? <p className="mt-2 text-xs leading-snug text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
