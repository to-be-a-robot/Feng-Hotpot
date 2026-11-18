import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/30 px-6 py-14 text-center", className)}>
      <span className="flex size-11 items-center justify-center rounded-full bg-card text-muted-foreground shadow-sm">
        <Icon className="size-5" />
      </span>
      <div className="space-y-1">
        <p className="font-display text-lg tracking-tight text-foreground">{title}</p>
        {description ? <p className="mx-auto max-w-sm text-[13px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function SectionTitle({
  children,
  action,
  className,
}: {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-3", className)}>
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{children}</h2>
      {action}
    </div>
  );
}
