import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, Check, Languages, Megaphone, Search, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { CreatorAvatar } from "@/components/app/Identity";
import { ScoreRing } from "@/components/app/ScoreRing";
import { OCCASIONS } from "@/lib/demo";
import type { Lang, LocationSlug } from "@/lib/types";
import { addDays, cn, compactNumber, isoDay, money, pluralize } from "@/lib/utils";
import { useApp } from "@/store/AppStore";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preselect?: string[];
}

export function NewCampaignDialog({ open, onOpenChange, preselect }: Props) {
  const { location, creatorsHere, createCampaign, notify } = useApp();
  const navigate = useNavigate();

  const today = isoDay(new Date());
  const [name, setName] = useState("");
  const [occasionId, setOccasionId] = useState(OCCASIONS[2]?.id ?? "");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(isoDay(addDays(new Date(), 21)));
  const [languages, setLanguages] = useState<Lang[]>(["en", "zh"]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});

  const preselectKey = (preselect ?? []).join(",");
  useEffect(() => {
    if (open) setSelected(preselectKey ? preselectKey.split(",") : []);
  }, [open, preselectKey]);

  const occasion = OCCASIONS.find((item) => item.id === occasionId);
  const creators = useMemo(() => creatorsHere(location), [creatorsHere, location]);
  const visible = creators.filter(
    (creator) =>
      creator.handle.toLowerCase().includes(query.toLowerCase()) ||
      (creator.display_name ?? "").toLowerCase().includes(query.toLowerCase()),
  );

  const reset = () => {
    setName("");
    setSelected([]);
    setQuery("");
    setFields({});
    setStart(today);
    setEnd(isoDay(addDays(new Date(), 21)));
    setLanguages(["en", "zh"]);
  };

  const toggleLanguage = (lang: Lang) => {
    setLanguages((prev) => (prev.includes(lang) ? prev.filter((item) => item !== lang) : [...prev, lang]));
  };

  const submit = () => {
    const result = createCampaign({
      name,
      occasion_id: occasionId,
      location: location as LocationSlug,
      start_date: start,
      end_date: end,
      creator_ids: selected,
      languages,
    });
    if (!result.ok) {
      setFields(result.error.fields ?? {});
      notify({ title: result.error.message, tone: "error" });
      return;
    }
    const { campaign, skipped } = result.data;
    setFields({});
    reset();
    onOpenChange(false);
    notify({
      title: `${campaign.name} is live`,
      description: `${pluralize(campaign.creators.length, "creator")} · ${pluralize(campaign.generation.total, "draft")} written${
        skipped.length ? ` · ${skipped.length} skipped` : ""
      }`,
      tone: "success",
    });
    navigate(`/campaigns/${campaign.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Start a campaign</DialogTitle>
          <DialogDescription>
            Pick the occasion and the creators. Codes and first drafts are created for every creator and language.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 pb-5">
          <div className="grid gap-3 sm:grid-cols-[1.4fr_1fr]">
            <label className="space-y-1.5">
              <span className="text-[12px] font-medium text-foreground">Campaign name</span>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={occasion ? `${occasion.name} · ${new Date(start).toLocaleDateString("en-US", { month: "short" })}` : "Cold week, hot pot"}
                maxLength={80}
                aria-invalid={Boolean(fields.name)}
              />
              {fields.name ? <span className="text-[11px] text-destructive">{fields.name}</span> : null}
            </label>
            <label className="space-y-1.5">
              <span className="text-[12px] font-medium text-foreground">Occasion</span>
              <Select value={occasionId} onChange={(event) => setOccasionId(event.target.value)}>
                {OCCASIONS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.name_zh}
                  </option>
                ))}
              </Select>
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="space-y-1.5">
              <span className="text-[12px] font-medium text-foreground">Starts</span>
              <Input type="date" value={start} min={today} onChange={(event) => setStart(event.target.value)} />
            </label>
            <label className="space-y-1.5">
              <span className="text-[12px] font-medium text-foreground">Ends</span>
              <Input type="date" value={end} min={start} onChange={(event) => setEnd(event.target.value)} />
              {fields.end_date ? <span className="text-[11px] text-destructive">{fields.end_date}</span> : null}
            </label>
            <div className="space-y-1.5">
              <span className="text-[12px] font-medium text-foreground">Draft languages</span>
              <div className="flex gap-1.5">
                {(["en", "zh"] as Lang[]).map((lang) => (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => toggleLanguage(lang)}
                    className={cn(
                      "inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md border text-[12px] font-medium transition-colors",
                      languages.includes(lang)
                        ? "border-primary/30 bg-primary-soft text-primary"
                        : "border-border bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Languages className="size-3.5" />
                    {lang === "en" ? "English" : "中文"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {occasion ? (
            <div className="rounded-md border border-border/70 bg-muted/40 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">The offer, copied onto every code</p>
              <p className="mt-1 font-display text-[15px] text-foreground">
                {occasion.offer_title.en} <span className="font-han text-[13px] text-muted-foreground">· {occasion.offer_title.zh}</span>
              </p>
              <p className="text-[12px] text-muted-foreground">
                {occasion.offer_details.en} · Return code valid for {occasion.return_valid_days} days from the next local day
              </p>
            </div>
          ) : null}

          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[12px] font-medium text-foreground">
                <Users className="size-3.5 text-primary" />
                Creators
                <span className="text-muted-foreground">({selected.length} of 25)</span>
              </span>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search handles"
                  className="h-8 w-[180px] pl-8 text-[12px]"
                />
              </div>
            </div>
            {fields.creator_ids ? <span className="text-[11px] text-destructive">{fields.creator_ids}</span> : null}
            <div className="max-h-[240px] space-y-1 overflow-y-auto rounded-md border border-border/70 p-1">
              {visible.map((creator) => {
                const active = selected.includes(creator.id);
                return (
                  <button
                    key={creator.id}
                    type="button"
                    onClick={() =>
                      setSelected((prev) => (active ? prev.filter((id) => id !== creator.id) : prev.length >= 25 ? prev : [...prev, creator.id]))
                    }
                    className={cn(
                      "flex w-full items-center gap-3 rounded-sm px-2 py-1.5 text-left transition-colors",
                      active ? "bg-primary-soft" : "hover:bg-muted",
                    )}
                  >
                    <CreatorAvatar handle={creator.handle} platform={creator.platform} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-foreground">{creator.handle}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {creator.city} · {compactNumber(creator.followers)} followers
                      </span>
                    </span>
                    <ScoreRing score={creator.score} size={28} strokeWidth={3} />
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                        active ? "border-primary bg-primary text-primary-foreground" : "border-border text-transparent",
                      )}
                    >
                      <Check className="size-3" />
                    </span>
                  </button>
                );
              })}
              {visible.length === 0 ? (
                <p className="px-2 py-4 text-center text-[12px] text-muted-foreground">No creators in this location yet.</p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <CalendarDays className="size-3.5" /> Max 90 days
            </span>
            <span className="flex items-center gap-1.5">
              <Megaphone className="size-3.5" /> One campaign per creator at a time
            </span>
            {occasion ? <span className="ml-auto">Comp per creator: {money(occasion.default_cost_cents)}</span> : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit}>Create campaign</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
