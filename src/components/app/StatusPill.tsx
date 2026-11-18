import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { statusLabel } from "@/lib/utils";
import type { BadgeProps } from "@/components/ui/badge";

const map: Record<string, { variant: BadgeProps["variant"]; spinning?: boolean }> = {
  draft: { variant: "warning" },
  approved: { variant: "jade" },
  sent: { variant: "neutral" },
  replied: { variant: "success" },
  declined: { variant: "muted" },
  rejected: { variant: "destructive" },
  ready: { variant: "success" },
  pending: { variant: "primary", spinning: true },
  running: { variant: "primary", spinning: true },
  failed: { variant: "destructive" },
  active: { variant: "success" },
  ended: { variant: "muted" },
  none: { variant: "outline" },
  done: { variant: "jade" },
  partial: { variant: "warning" },
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const style = map[status] ?? { variant: "neutral" as const };
  return (
    <Badge variant={style.variant} className={className}>
      {style.spinning ? <Loader2 className="animate-spin" /> : null}
      {statusLabel(status)}
    </Badge>
  );
}
