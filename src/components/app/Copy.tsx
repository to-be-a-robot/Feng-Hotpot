import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function CopyButton({ value, label, className }: { value: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        if (await copy(value)) {
          setDone(true);
          window.setTimeout(() => setDone(false), 1600);
        }
      }}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        className,
      )}
      aria-label={label ?? "Copy"}
    >
      {done ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      {label ? <span>{done ? "Copied" : label}</span> : null}
    </button>
  );
}

export function CodeChip({ value, className }: { value: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border border-border/80 bg-muted/60 py-1 pl-2 pr-1 font-mono text-[11px] font-medium tracking-tight text-foreground",
        className,
      )}
    >
      {value}
      <CopyButton value={value} label="" className="px-1 py-0.5" />
    </span>
  );
}
