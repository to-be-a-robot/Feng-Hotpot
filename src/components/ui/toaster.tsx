import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useApp } from "@/store/AppStore";
import { cn } from "@/lib/utils";

const icon = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
};

export function Toaster() {
  const { toast, dismissToast } = useApp();
  if (!toast) return null;
  const Icon = icon[toast.tone];

  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-[60] w-full max-w-sm -translate-x-1/2 px-4">
      <div
        key={toast.id}
        role="status"
        className={cn(
          "pointer-events-auto flex animate-fade-up items-start gap-3 rounded-lg border bg-popover p-3.5 shadow-elegant",
          toast.tone === "error" ? "border-destructive/30" : toast.tone === "success" ? "border-success/30" : "border-border",
        )}
      >
        <Icon
          className={cn(
            "mt-0.5 size-4 shrink-0",
            toast.tone === "error" ? "text-destructive" : toast.tone === "success" ? "text-success" : "text-accent",
          )}
        />
        <div className="flex-1 space-y-0.5">
          <p className="text-sm font-medium leading-snug text-foreground">{toast.title}</p>
          {toast.description ? <p className="text-xs leading-relaxed text-muted-foreground">{toast.description}</p> : null}
        </div>
        <button
          onClick={dismissToast}
          className="rounded-sm p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Dismiss"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  );
}
