import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
  count?: number;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "default",
  className,
}: {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "default";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex w-full items-center gap-0.5 rounded-md border border-border/70 bg-muted/60 p-0.5",
        size === "sm" ? "text-[12px]" : "text-[13px]",
        className,
      )}
      role="tablist"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-sm px-2.5 font-medium transition-all",
              size === "sm" ? "h-7" : "h-8",
              active
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-card/60 hover:text-foreground",
            )}
          >
            {option.label}
            {option.count != null ? (
              <span
                className={cn(
                  "rounded-full px-1.5 text-[10px] font-semibold tabular",
                  active ? "bg-primary-soft text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {option.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
