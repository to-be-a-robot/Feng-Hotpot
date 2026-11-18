import { SCORE_FEATURES, SCORE_WEIGHTS, cn } from "@/lib/utils";
import { scoreTone } from "./ScoreRing";

export function ScoreBars({ breakdown }: { breakdown: Record<string, number | null> }) {
  return (
    <div className="space-y-2.5">
      {SCORE_FEATURES.map((feature) => {
        const value = breakdown[feature.key];
        const tone = scoreTone((value ?? 0) * 100);
        return (
          <div key={feature.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-foreground">{feature.label}</span>
              <span className="text-[11px] tabular text-muted-foreground">
                {value == null ? "unknown" : `${Math.round(value * 100)}`}
                <span className="ml-1.5 opacity-60">{Math.round((SCORE_WEIGHTS[feature.key] ?? 0) * 100)}% weight</span>
              </span>
            </div>
            <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full transition-[width] duration-700", tone.bar)}
                style={{ width: `${Math.round((value ?? 0) * 100)}%` }}
              />
            </div>
            <p className="col-span-2 text-[11px] leading-snug text-muted-foreground">{feature.hint}</p>
          </div>
        );
      })}
    </div>
  );
}
