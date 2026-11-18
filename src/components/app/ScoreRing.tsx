import { cn } from "@/lib/utils";

export function scoreTone(score: number) {
  if (score >= 80) return { bar: "bg-success", text: "text-success", ring: "stroke-success" };
  if (score >= 65) return { bar: "bg-gold", text: "text-gold", ring: "stroke-gold" };
  if (score >= 45) return { bar: "bg-warning", text: "text-warning", ring: "stroke-warning" };
  return { bar: "bg-destructive", text: "text-destructive", ring: "stroke-destructive" };
}

interface ScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  showLabel?: boolean;
  className?: string;
}

export function ScoreRing({ score, size = 44, strokeWidth = 4, showLabel = true, className }: ScoreRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const tone = scoreTone(clamped);

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={strokeWidth} className="stroke-border/70" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          className={cn("transition-[stroke-dashoffset] duration-700", tone.ring)}
        />
      </svg>
      {showLabel ? (
        <span className={cn("absolute font-semibold tabular", tone.text, size >= 56 ? "text-base" : "text-xs")}>{clamped}</span>
      ) : null}
      <span className="sr-only">Score {clamped} out of 100</span>
    </div>
  );
}
