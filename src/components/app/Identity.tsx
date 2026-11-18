import { cn, initials, platformLabel } from "@/lib/utils";

const platformStyles: Record<string, string> = {
  instagram: "bg-primary-soft text-primary",
  tiktok: "bg-foreground/[0.06] text-foreground",
  xhs: "bg-destructive/10 text-destructive",
};

const platformMonogram: Record<string, string> = {
  instagram: "IG",
  tiktok: "TT",
  xhs: "XHS",
};

export function PlatformMark({ platform, className }: { platform: string; className?: string }) {
  const key = platform.toLowerCase();
  return (
    <span
      title={platformLabel(platform)}
      className={cn(
        "inline-flex h-6 min-w-6 items-center justify-center rounded-sm px-1.5 text-[10px] font-bold tracking-wide",
        platformStyles[key] ?? "bg-muted text-muted-foreground",
        className,
      )}
    >
      {platformMonogram[key] ?? platform.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function CreatorAvatar({
  handle,
  platform,
  size = "md",
  className,
}: {
  handle: string;
  platform?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes = {
    sm: "size-8 text-[11px]",
    md: "size-10 text-xs",
    lg: "size-14 text-base",
  };
  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <span
        className={cn(
          "flex items-center justify-center rounded-full border border-border/70 bg-gradient-surface font-semibold tracking-wide text-foreground",
          sizes[size],
        )}
      >
        {initials(handle)}
      </span>
      {platform ? (
        <span className="absolute -bottom-1 -right-1 rounded-full bg-card p-0.5 shadow-sm">
          <PlatformMark platform={platform} className="h-4 min-w-4 rounded-full px-1 text-[8px]" />
        </span>
      ) : null}
    </span>
  );
}
