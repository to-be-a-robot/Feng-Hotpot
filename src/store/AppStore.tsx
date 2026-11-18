import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  BRIEFS,
  CAMPAIGNS,
  CREATORS,
  CODE_PREFIXES,
  DEMO_USER,
  LOCATIONS,
  OCCASIONS,
  OUTREACH,
  REDEMPTIONS,
  REDEMPTION_LOCATIONS,
  newRedemptionCode,
} from "@/lib/demo";
import { draftFor, hasCode } from "@/lib/drafts";
import type {
  Brief,
  Campaign,
  CampaignCreator,
  Creator,
  Lang,
  LocationSlug,
  Outreach,
  OutreachStatus,
  RecentRedemption,
  RedemptionResult,
  Role,
} from "@/lib/types";
import { addDays, isToday, isoDay, randomCode } from "@/lib/utils";

const STORAGE_KEY = "feng-creator-loop-demo-v1";

interface ReturnCode {
  code: string;
  campaign_id: string;
  campaign_creator_id: string;
  parent_redemption_id: string;
  starts_at: string;
  expires_at: string;
}

interface State {
  role: Role;
  location: LocationSlug;
  creators: Creator[];
  campaigns: Campaign[];
  outreach: Outreach[];
  redemptions: RecentRedemption[];
  redemptionLocations: Record<string, string>;
  returnCodes: ReturnCode[];
  briefs: Brief[];
}

const initialState: State = {
  role: "manager",
  location: "sunnyvale",
  creators: CREATORS,
  campaigns: CAMPAIGNS,
  outreach: OUTREACH,
  redemptions: REDEMPTIONS,
  redemptionLocations: REDEMPTION_LOCATIONS,
  returnCodes: [],
  briefs: BRIEFS,
};

function loadState(): State {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return initialState;
    const parsed = JSON.parse(raw) as Partial<State>;
    if (!parsed.campaigns?.length) return initialState;
    return { ...initialState, ...parsed };
  } catch {
    return initialState;
  }
}

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: "success" | "error" | "info";
}

export interface ApiFailure {
  ok: false;
  error: { code: string; message: string; fields?: Record<string, string> };
}

export type Result<T> = { ok: true; data: T } | ApiFailure;

interface CreateCampaignInput {
  name: string;
  occasion_id: string;
  location: LocationSlug;
  start_date: string;
  end_date: string;
  creator_ids: string[];
  languages: Lang[];
}

interface AppStore {
  state: State;
  role: Role;
  location: LocationSlug;
  locationMeta: (typeof LOCATIONS)[number];
  user: typeof DEMO_USER;
  toast: Toast | null;
  setRole: (role: Role) => void;
  setLocation: (location: LocationSlug) => void;
  notify: (toast: Omit<Toast, "id">) => void;
  dismissToast: () => void;
  resetDemo: () => void;
  creatorsHere: (location?: LocationSlug) => Creator[];
  campaignsHere: (location?: LocationSlug) => Campaign[];
  campaignById: (id: string) => Campaign | undefined;
  outreachForCampaign: (id: string) => Outreach[];
  activeCampaignsForCreator: (creatorId: string) => { id: string; name: string }[];
  summary: (location?: LocationSlug) => {
    drafts_waiting: number;
    approved_unsent: number;
    active_campaigns: number;
    redemptions_today: number;
  };
  createCampaign: (input: CreateCampaignInput) => Result<{ campaign: Campaign; skipped: { creator_id: string; reason: string }[] }>;
  outreachAction: (
    id: string,
    action: "edit" | "approve" | "reject" | "reopen" | "mark_sent" | "mark_replied" | "mark_declined",
    payload?: { version?: number; editedText?: string; reason?: string },
  ) => Result<Outreach>;
  regenerateOutreach: (id: string, version: number) => Result<Outreach>;
  updateCampaignCreator: (
    campaignId: string,
    ccId: string,
    patch: { post_url?: string | null; post_date?: string | null; cost_cents?: number | null; version: number },
  ) => Result<CampaignCreator>;
  redeem: (input: { code: string; party_size: number; location?: LocationSlug }) => Result<RedemptionResult>;
  voidRedemption: (id: string, reason: string) => Result<RecentRedemption>;
  offerForCode: (code: string) =>
    | { status: "active" | "not_started" | "expired"; offer: { title: Record<Lang, string>; details: Record<Lang, string>; starts: string; ends: string; kind: string }; restaurant: { name: string; location_name: string; address: string | null }; recommended_by: string | null; return_title: Record<Lang, string> }
    | null;
  latestBrief: (location?: LocationSlug) => Brief | undefined;
  briefsHere: (location?: LocationSlug) => Brief[];
}

const StoreContext = createContext<AppStore | null>(null);

function recalculate(campaign: Campaign, outreach: Outreach[]): Campaign {
  const rows = outreach.filter((item) => item.campaign_id === campaign.id);
  const creators = campaign.creators.map((cc) => {
    const counts: Record<OutreachStatus, number> = {
      draft: 0,
      approved: 0,
      sent: 0,
      replied: 0,
      declined: 0,
      rejected: 0,
    };
    for (const item of rows) {
      if (item.campaign_creator_id === cc.campaign_creator_id) counts[item.status] += 1;
    }
    return { ...cc, outreach_summary: { ...counts } };
  });
  return {
    ...campaign,
    creators,
    totals: {
      first_visits: creators.reduce((sum, cc) => sum + cc.first_visits, 0),
      return_visits: creators.reduce((sum, cc) => sum + cc.return_visits, 0),
      cost_cents: creators.reduce((sum, cc) => sum + (cc.cost_cents ?? 0), 0),
      includes_simulated: campaign.is_simulated || creators.some((cc) => cc.is_simulated),
    },
    generation: {
      status:
        rows.length === 0
          ? "none"
          : rows.some((row) => row.generation_status === "pending")
            ? "running"
            : rows.some((row) => row.generation_status === "failed")
              ? "partial"
              : "done",
      total: rows.length,
      done: rows.filter((row) => row.generation_status === "ready").length,
      failed: rows.filter((row) => row.generation_status === "failed").length,
    },
  };
}

let toastId = 0;

export function AppStoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(loadState);
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* demo state only — a full quota should not break the UI */
    }
  }, [state]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const notify = useCallback((next: Omit<Toast, "id">) => {
    toastId += 1;
    setToast({ ...next, id: toastId });
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  const setRole = useCallback((role: Role) => setState((prev) => ({ ...prev, role })), []);
  const setLocation = useCallback((location: LocationSlug) => setState((prev) => ({ ...prev, location })), []);

  const resetDemo = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    setState({ ...initialState, creators: CREATORS, campaigns: CAMPAIGNS, outreach: OUTREACH, redemptions: REDEMPTIONS });
    notify({ title: "Demo data reset", description: "Campaigns, drafts and visits are back to the seeded story.", tone: "info" });
  }, [notify]);

  const creatorsHere = useCallback(
    (location?: LocationSlug) => {
      const slug = location ?? state.location;
      const meta = LOCATIONS.find((item) => item.slug === slug) ?? LOCATIONS[0];
      const cities = meta.creator_cities.map((city) => city.toLowerCase());
      return state.creators
        .filter((creator) => cities.includes(creator.city.toLowerCase()))
        .sort((a, b) => b.score - a.score);
    },
    [state.location, state.creators],
  );

  const campaignsHere = useCallback(
    (location?: LocationSlug) => {
      const slug = location ?? state.location;
      return [...state.campaigns]
        .filter((campaign) => campaign.location === slug)
        .sort((a, b) => (a.start_date < b.start_date ? 1 : -1));
    },
    [state.location, state.campaigns],
  );

  const campaignById = useCallback((id: string) => state.campaigns.find((campaign) => campaign.id === id), [state.campaigns]);

  const outreachForCampaign = useCallback(
    (id: string) => state.outreach.filter((item) => item.campaign_id === id),
    [state.outreach],
  );

  const activeCampaignsForCreator = useCallback(
    (creatorId: string) =>
      state.campaigns
        .filter((campaign) => campaign.status === "active" && campaign.creators.some((cc) => cc.creator.id === creatorId))
        .map((campaign) => ({ id: campaign.id, name: campaign.name })),
    [state.campaigns],
  );

  const summary = useCallback(
    (location?: LocationSlug) => {
      const slug = location ?? state.location;
      const campaignIds = new Set(state.campaigns.filter((campaign) => campaign.location === slug).map((campaign) => campaign.id));
      const rows = state.outreach.filter((item) => campaignIds.has(item.campaign_id));
      return {
        drafts_waiting: rows.filter((item) => item.status === "draft" && item.generation_status === "ready").length,
        approved_unsent: rows.filter((item) => item.status === "approved").length,
        active_campaigns: state.campaigns.filter((campaign) => campaign.location === slug && campaign.status === "active").length,
        redemptions_today: state.redemptions.filter(
          (item) => (state.redemptionLocations[item.id] ?? "sunnyvale") === slug && !item.voided_at && isToday(item.redeemed_at),
        ).length,
      };
    },
    [state.campaigns, state.location, state.outreach, state.redemptions, state.redemptionLocations],
  );

  const createCampaign = useCallback<AppStore["createCampaign"]>(
    (input) => {
      const occasion = OCCASIONS.find((item) => item.id === input.occasion_id || item.slug === input.occasion_id);
      if (!occasion) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Choose an occasion.", fields: { occasion_id: "Choose an occasion" } } };
      }
      const name = input.name.trim();
      if (name.length < 3) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { name: "Must be 3–80 characters" } } };
      }
      if (!input.start_date || !input.end_date) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { start_date: "Pick both dates" } } };
      }
      if (input.start_date > input.end_date) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { end_date: "Must be on or after the start date" } } };
      }
      if (input.creator_ids.length < 1 || input.creator_ids.length > 25) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Choose 1–25 creators.", fields: { creator_ids: "Choose 1–25 creators" } } };
      }
      if (input.languages.length === 0) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Choose at least one language.", fields: { languages: "Choose English, Chinese or both" } } };
      }

      const id = `k_${randomCode("", 6).toLowerCase()}`;
      const prefix = CODE_PREFIXES[occasion.slug] ?? "DEAL";
      const skipped: { creator_id: string; reason: string }[] = [];
      const newOutreach: Outreach[] = [];
      const newCodes: ReturnCode[] = [];
      const creators: CampaignCreator[] = [];

      for (const creatorId of input.creator_ids) {
        const creator = state.creators.find((item) => item.id === creatorId);
        if (!creator) {
          skipped.push({ creator_id: creatorId, reason: "CREATOR_NOT_FOUND" });
          continue;
        }
        const ccId = `cc_${id}_${creatorId}`;
        const code = randomCode(`FENG-${prefix}-`, 6);
        const expires = addDays(new Date(input.end_date), occasion.return_valid_days);
        creators.push({
          campaign_creator_id: ccId,
          version: 1,
          creator: { id: creator.id, handle: creator.handle, platform: creator.platform, profile_url: creator.profile_url },
          code: { value: code, url: `https://creator-loop.example/r/${code}`, expires_at: expires.toISOString() },
          outreach_summary: { draft: 0, approved: 0, sent: 0, replied: 0, declined: 0, rejected: 0 },
          post_url: null,
          post_date: null,
          cost_cents: occasion.default_cost_cents,
          first_visits: 0,
          return_visits: 0,
          is_simulated: false,
        });
        for (const lang of input.languages) {
          const text = draftFor({ creator, occasion, code, lang, variant: Math.floor(Math.random() * 3) });
          newOutreach.push({
            id: `o_${randomCode("", 8).toLowerCase()}`,
            version: 1,
            campaign_id: id,
            campaign_creator_id: ccId,
            creator: {
              id: creator.id,
              handle: creator.handle,
              platform: creator.platform,
              profile_url: creator.profile_url,
              followers: creator.followers,
            },
            platform: creator.platform,
            lang,
            draft_text: text,
            edited_text: null,
            current_text: text,
            status: "draft",
            has_offer_link: hasCode(text, code),
            referenced_posts: creator.recent_posts.slice(0, 2),
            generation_status: "ready",
            reject_reason: null,
            approver: null,
            decided_at: null,
            sent_at: null,
            replied_at: null,
            updated_at: new Date().toISOString(),
            is_simulated: false,
          });
        }
      }

      const campaign: Campaign = {
        id,
        name,
        occasion: { id: occasion.id, slug: occasion.slug, name: occasion.name },
        location: input.location,
        start_date: input.start_date,
        end_date: input.end_date,
        status: "active",
        offer: { title: occasion.offer_title.en, title_zh: occasion.offer_title.zh, value_cents: occasion.default_cost_cents },
        generation: { status: newOutreach.length ? "done" : "none", total: newOutreach.length, done: newOutreach.length, failed: 0 },
        totals: { first_visits: 0, return_visits: 0, cost_cents: creators.reduce((sum, cc) => sum + (cc.cost_cents ?? 0), 0), includes_simulated: false },
        creators,
        is_simulated: false,
      };

      setState((prev) => ({
        ...prev,
        campaigns: [campaign, ...prev.campaigns],
        outreach: [...newOutreach, ...prev.outreach],
        returnCodes: [...prev.returnCodes, ...newCodes],
      }));

      return { ok: true, data: { campaign: recalculate(campaign, newOutreach), skipped } };
    },
    [state.creators],
  );

  const outreachAction = useCallback<AppStore["outreachAction"]>(
    (id, action, payload) => {
      const item = state.outreach.find((row) => row.id === id);
      if (!item) return { ok: false, error: { code: "NOT_FOUND", message: "We couldn't find that message." } };

      const target: Record<typeof action, OutreachStatus> = {
        edit: "draft",
        approve: "approved",
        reject: "rejected",
        reopen: "draft",
        mark_sent: "sent",
        mark_replied: "replied",
        mark_declined: "declined",
      };
      const allowed: Record<typeof action, OutreachStatus[]> = {
        edit: ["draft", "approved"],
        approve: ["draft"],
        reject: ["draft", "approved"],
        reopen: ["approved", "rejected"],
        mark_sent: ["approved"],
        mark_replied: ["sent"],
        mark_declined: ["sent", "replied"],
      };

      if (action !== "edit" && item.status === target[action]) {
        return { ok: true, data: item };
      }
      if (payload?.version != null && payload.version !== item.version) {
        return { ok: false, error: { code: "STALE_VERSION", message: "Someone else changed this draft." } };
      }
      if (!allowed[action].includes(item.status)) {
        return { ok: false, error: { code: "INVALID_TRANSITION", message: "That action isn't available for this message's status." } };
      }

      const now = new Date().toISOString();
      const text = action === "edit" ? (payload?.editedText ?? "").trim() : item.edited_text ?? item.draft_text;
      if (action === "edit" && (text.length < 1 || text.length > 2000)) {
        return {
          ok: false,
          error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { edited_text: "Message must be 1–2000 characters" } },
        };
      }
      if (action === "approve" && (text.trim().length < 1 || text.length > 2000)) {
        return {
          ok: false,
          error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { text: "The message is empty or longer than 2000 characters" } },
        };
      }
      if (action === "reject" && (payload?.reason ?? "").length > 280) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { reason: "Up to 280 characters" } } };
      }

      const next: Outreach = {
        ...item,
        version: item.version + 1,
        status: target[action],
        edited_text: action === "edit" ? text : item.edited_text,
        current_text: action === "edit" ? text : item.edited_text ?? item.draft_text,
        has_offer_link: (() => {
          const campaign = state.campaigns.find((row) => row.id === item.campaign_id);
          const cc = campaign?.creators.find((row) => row.campaign_creator_id === item.campaign_creator_id);
          return cc?.code ? hasCode(text, cc.code.value) : false;
        })(),
        approver: action === "approve" || action === "reject" ? (DEMO_USER.display_name ?? "Tyler Wu") : action === "reopen" ? null : item.approver,
        decided_at: action === "approve" || action === "reject" ? now : action === "reopen" ? null : item.decided_at,
        reject_reason: action === "reject" ? (payload?.reason?.trim() || null) : action === "reopen" ? null : item.reject_reason,
        sent_at: action === "mark_sent" ? now : item.sent_at,
        replied_at: action === "mark_replied" || action === "mark_declined" ? item.replied_at ?? now : item.replied_at,
        updated_at: now,
      };

      setState((prev) => ({
        ...prev,
        outreach: prev.outreach.map((row) => (row.id === id ? next : row)),
        campaigns: prev.campaigns.map((campaign) =>
          campaign.id === item.campaign_id
            ? recalculate(campaign, prev.outreach.map((row) => (row.id === id ? next : row)))
            : campaign,
        ),
      }));

      return { ok: true, data: next };
    },
    [state.campaigns, state.outreach],
  );

  const regenerateOutreach = useCallback<AppStore["regenerateOutreach"]>(
    (id, version) => {
      const item = state.outreach.find((row) => row.id === id);
      if (!item) return { ok: false, error: { code: "NOT_FOUND", message: "We couldn't find that message." } };
      if (version !== item.version) {
        return { ok: false, error: { code: "STALE_VERSION", message: "Someone else changed this draft." } };
      }
      if (!["draft", "approved", "rejected"].includes(item.status)) {
        return { ok: false, error: { code: "INVALID_TRANSITION", message: "Messages that were sent can't be rewritten." } };
      }
      const pending: Outreach = { ...item, version: item.version + 1, status: "draft", generation_status: "pending", draft_text: "", edited_text: null, current_text: "" };
      setState((prev) => ({ ...prev, outreach: prev.outreach.map((row) => (row.id === id ? pending : row)) }));

      window.setTimeout(() => {
        setState((prev) => {
          const current = prev.outreach.find((row) => row.id === id);
          if (!current) return prev;
          const campaign = prev.campaigns.find((row) => row.id === current.campaign_id);
          const cc = campaign?.creators.find((row) => row.campaign_creator_id === current.campaign_creator_id);
          const creator = prev.creators.find((row) => row.id === current.creator.id);
          const occasion = OCCASIONS.find((row) => row.slug === campaign?.occasion.slug);
          if (!creator || !occasion || !cc?.code) return prev;
          const text = draftFor({
            creator,
            occasion,
            code: cc.code.value,
            lang: current.lang,
            variant: Math.floor(Math.random() * 3),
          });
          const ready: Outreach = {
            ...current,
            version: current.version + 1,
            generation_status: "ready",
            draft_text: text,
            current_text: text,
            has_offer_link: true,
            updated_at: new Date().toISOString(),
          };
          return { ...prev, outreach: prev.outreach.map((row) => (row.id === id ? ready : row)) };
        });
      }, 1100);

      return { ok: true, data: pending };
    },
    [state.outreach],
  );

  const updateCampaignCreator = useCallback<AppStore["updateCampaignCreator"]>(
    (campaignId, ccId, patch) => {
      const campaign = state.campaigns.find((row) => row.id === campaignId);
      const cc = campaign?.creators.find((row) => row.campaign_creator_id === ccId);
      if (!campaign || !cc) return { ok: false, error: { code: "NOT_FOUND", message: "We couldn't find that creator." } };
      if (campaign.status === "ended") {
        return { ok: false, error: { code: "INVALID_TRANSITION", message: "This campaign has ended and can't be edited." } };
      }
      if (patch.version !== cc.version) {
        return { ok: false, error: { code: "STALE_VERSION", message: "Someone else changed this row." } };
      }
      const fields: Record<string, string> = {};
      if (patch.post_url != null && patch.post_url !== "" && !/^https:\/\/\S+$/.test(patch.post_url)) {
        fields.post_url = "Use a link that starts with https://";
      }
      if (patch.cost_cents != null && (!Number.isInteger(patch.cost_cents) || patch.cost_cents < 0 || patch.cost_cents > 1_000_000)) {
        fields.cost_cents = "Whole cents, 0 to 1,000,000";
      }
      if (Object.keys(fields).length) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields } };
      }

      const next: CampaignCreator = {
        ...cc,
        version: cc.version + 1,
        post_url: "post_url" in patch ? patch.post_url || null : cc.post_url,
        post_date: "post_date" in patch ? patch.post_date || null : cc.post_date,
        cost_cents: "cost_cents" in patch ? patch.cost_cents ?? null : cc.cost_cents,
      };

      setState((prev) => ({
        ...prev,
        campaigns: prev.campaigns.map((row) =>
          row.id === campaignId
            ? {
                ...row,
                creators: row.creators.map((item) => (item.campaign_creator_id === ccId ? next : item)),
                totals: {
                  ...row.totals,
                  cost_cents:
                    row.creators.reduce((sum, item) => sum + (item.campaign_creator_id === ccId ? next.cost_cents ?? 0 : item.cost_cents ?? 0), 0),
                },
              }
            : row,
        ),
      }));

      return { ok: true, data: next };
    },
    [state.campaigns],
  );

  const redeem = useCallback<AppStore["redeem"]>(
    ({ code, party_size, location }) => {
      const normalized = code.trim().toUpperCase();
      const campaignList = state.campaigns;
      const today = new Date().toISOString();

      if (!normalized) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Enter a code.", fields: { code: "Enter the code on the guest's screen" } } };
      }
      if (!Number.isInteger(party_size) || party_size < 1 || party_size > 50) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Check the highlighted fields.", fields: { party_size: "Must be 1–50" } } };
      }

      const creatorMatch = campaignList
        .flatMap((campaign) => campaign.creators.map((cc) => ({ campaign, cc })))
        .find((entry) => entry.cc.code?.value.toUpperCase() === normalized);

      const returnMatch = state.returnCodes.find((entry) => entry.code === normalized);

      if (!creatorMatch && !returnMatch) {
        return { ok: false, error: { code: "CODE_INVALID", message: "That code isn't one of ours." } };
      }
      const campaign = creatorMatch?.campaign ?? campaignList.find((row) => row.id === returnMatch?.campaign_id);
      if (!campaign) {
        return { ok: false, error: { code: "CODE_INVALID", message: "That code isn't one of ours." } };
      }
      const slug = location ?? state.location;
      if (campaign.location !== slug) {
        return { ok: false, error: { code: "WRONG_LOCATION", message: `This code only works in ${campaign.location}.` } };
      }
      const cc = creatorMatch?.cc ?? campaign.creators.find((row) => row.campaign_creator_id === returnMatch?.campaign_creator_id);
      if (!cc) return { ok: false, error: { code: "CODE_INVALID", message: "That code isn't one of ours." } };

      if (creatorMatch && campaign.status === "ended") {
        return { ok: false, error: { code: "CODE_EXPIRED", message: "This campaign has ended." } };
      }
      if (returnMatch && new Date(returnMatch.expires_at) < new Date()) {
        return { ok: false, error: { code: "CODE_EXPIRED", message: "This return code has expired." } };
      }
      if (!returnMatch && (creatorMatch?.cc.code?.expires_at ?? today) < today) {
        return { ok: false, error: { code: "CODE_EXPIRED", message: "This code has expired." } };
      }

      const type = returnMatch ? "return" : "first";
      const redemptionId = `r_${randomCode("", 8).toLowerCase()}`;
      const returnCode: ReturnCode | null =
        type === "first"
          ? {
              code: newRedemptionCode("RET"),
              campaign_id: campaign.id,
              campaign_creator_id: cc.campaign_creator_id,
              parent_redemption_id: redemptionId,
              starts_at: addDays(new Date(), 1).toISOString(),
              expires_at: addDays(new Date(), 30).toISOString(),
            }
          : null;

      const result: RedemptionResult = {
        redemption: {
          id: redemptionId,
          type,
          visit_number: type === "first" ? cc.first_visits + 1 : cc.first_visits + cc.return_visits + 1,
          redeemed_at: today,
          location: campaign.location,
          party_size,
          creator_handle: cc.creator.handle,
          offer_title: campaign.offer.title,
          voided_at: null,
          is_simulated: false,
        },
        return_offer: returnCode
          ? {
              code: returnCode.code,
              url: `https://creator-loop.example/r/${returnCode.code}`,
              title: "Welcome back: free dessert",
              starts_at: returnCode.starts_at,
              expires_at: returnCode.expires_at,
            }
          : null,
      };

      const recent: RecentRedemption = {
        id: redemptionId,
        code: normalized,
        type,
        party_size,
        redeemed_at: today,
        voided_at: null,
        voided_reason: null,
        can_void_until: new Date(Date.now() + 15 * 60_000).toISOString(),
        has_return_offer: Boolean(returnCode),
        is_simulated: false,
      };

      setState((prev) => ({
        ...prev,
        redemptions: [recent, ...prev.redemptions],
        redemptionLocations: { ...prev.redemptionLocations, [redemptionId]: campaign.location },
        returnCodes: returnCode ? [...prev.returnCodes, returnCode] : prev.returnCodes,
        campaigns: prev.campaigns.map((row) =>
          row.id === campaign.id
            ? {
                ...row,
                creators: row.creators.map((item) =>
                  item.campaign_creator_id === cc.campaign_creator_id
                    ? {
                        ...item,
                        first_visits: type === "first" ? item.first_visits + 1 : item.first_visits,
                        return_visits: type === "return" ? item.return_visits + 1 : item.return_visits,
                      }
                    : item,
                ),
                totals: {
                  ...row.totals,
                  first_visits: row.totals.first_visits + (type === "first" ? 1 : 0),
                  return_visits: row.totals.return_visits + (type === "return" ? 1 : 0),
                },
              }
            : row,
        ),
      }));

      return { ok: true, data: result };
    },
    [state.campaigns, state.creators, state.location, state.returnCodes],
  );

  const voidRedemption = useCallback<AppStore["voidRedemption"]>(
    (id, reason) => {
      const row = state.redemptions.find((item) => item.id === id);
      if (!row) return { ok: false, error: { code: "NOT_FOUND", message: "We couldn't find that visit." } };
      if (row.voided_at) return { ok: false, error: { code: "INVALID_TRANSITION", message: "This visit is already voided." } };
      const reasonText = reason.trim();
      if (reasonText.length < 3) {
        return { ok: false, error: { code: "VALIDATION_FAILED", message: "Add a short reason.", fields: { reason: "Why is this being voided?" } } };
      }
      const next: RecentRedemption = { ...row, voided_at: new Date().toISOString(), voided_reason: reasonText, has_return_offer: false };
      const location = state.redemptionLocations[id] ?? state.location;

      setState((prev) => ({
        ...prev,
        redemptions: prev.redemptions.map((item) => (item.id === id ? next : item)),
        returnCodes: prev.returnCodes.filter((code) => code.parent_redemption_id !== id),
        campaigns: prev.campaigns.map((campaign) => {
          if (campaign.location !== location) return campaign;
          const creatorRow = campaign.creators.find((cc) => cc.code?.value === row.code || prev.returnCodes.some((rc) => rc.code === row.code && rc.campaign_creator_id === cc.campaign_creator_id));
          if (!creatorRow) return campaign;
          return {
            ...campaign,
            creators: campaign.creators.map((cc) =>
              cc.campaign_creator_id === creatorRow.campaign_creator_id
                ? {
                    ...cc,
                    first_visits: Math.max(0, cc.first_visits - (row.type === "first" ? 1 : 0)),
                    return_visits: Math.max(0, cc.return_visits - (row.type === "return" ? 1 : 0)),
                  }
                : cc,
            ),
            totals: {
              ...campaign.totals,
              first_visits: Math.max(0, campaign.totals.first_visits - (row.type === "first" ? 1 : 0)),
              return_visits: Math.max(0, campaign.totals.return_visits - (row.type === "return" ? 1 : 0)),
            },
          };
        }),
      }));

      return { ok: true, data: next };
    },
    [state.campaigns, state.location, state.redemptionLocations, state.redemptions, state.returnCodes],
  );

  const offerForCode = useCallback<AppStore["offerForCode"]>(
    (code) => {
      const normalized = code.trim().toUpperCase();
      for (const campaign of state.campaigns) {
        const cc = campaign.creators.find((row) => row.code?.value.toUpperCase() === normalized);
        if (!cc) continue;
        const occasion = OCCASIONS.find((row) => row.slug === campaign.occasion.slug);
        const locationMeta = LOCATIONS.find((row) => row.slug === campaign.location);
        const now = new Date();
        const expires = cc.code ? new Date(cc.code.expires_at) : now;
        const status = now > expires ? "expired" : "active";
        return {
          status,
          offer: {
            title: { en: campaign.offer.title, zh: campaign.offer.title_zh },
            details: {
              en: occasion?.offer_details.en ?? "One per table · Dine-in",
              zh: occasion?.offer_details.zh ?? "每桌限一份 · 仅限堂食",
            },
            starts: campaign.start_date,
            ends: isoDay(expires),
            kind: "creator",
          },
          restaurant: {
            name: "Feng Hotpot",
            location_name: locationMeta?.name ?? campaign.location,
            address: locationMeta?.address ?? null,
          },
          recommended_by: cc.creator.handle,
          return_title: { en: "Welcome back: free dessert", zh: "欢迎回来：免费甜点" },
        };
      }
      const ret = state.returnCodes.find((row) => row.code === normalized);
      if (ret) {
        const campaign = state.campaigns.find((row) => row.id === ret.campaign_id);
        const locationMeta = LOCATIONS.find((row) => row.slug === campaign?.location);
        const now = new Date();
        return {
          status: now > new Date(ret.expires_at) ? "expired" : now < new Date(ret.starts_at) ? "not_started" : "active",
          offer: {
            title: { en: "Welcome back: free dessert", zh: "欢迎回来：免费甜点" },
            details: { en: "One use · Dine-in", zh: "限用一次 · 仅限堂食" },
            starts: isoDay(new Date(ret.starts_at)),
            ends: isoDay(new Date(ret.expires_at)),
            kind: "return",
          },
          restaurant: {
            name: "Feng Hotpot",
            location_name: locationMeta?.name ?? campaign?.location ?? "",
            address: locationMeta?.address ?? null,
          },
          recommended_by: null,
          return_title: { en: "Welcome back: free dessert", zh: "欢迎回来：免费甜点" },
        };
      }
      return null;
    },
    [state.campaigns, state.returnCodes],
  );

  const latestBrief = useCallback(
    (location?: LocationSlug) => {
      const slug = location ?? state.location;
      return state.briefs
        .filter((brief) => brief.location === slug)
        .sort((a, b) => (a.week_of < b.week_of ? 1 : -1))[0];
    },
    [state.briefs, state.location],
  );

  const briefsHere = useCallback(
    (location?: LocationSlug) => {
      const slug = location ?? state.location;
      return state.briefs.filter((brief) => brief.location === slug).sort((a, b) => (a.week_of < b.week_of ? 1 : -1));
    },
    [state.briefs, state.location],
  );

  const locationMeta = LOCATIONS.find((item) => item.slug === state.location) ?? LOCATIONS[0];

  const value = useMemo<AppStore>(
    () => ({
      state,
      role: state.role,
      location: state.location,
      locationMeta,
      user: DEMO_USER,
      toast,
      setRole,
      setLocation,
      notify,
      dismissToast,
      resetDemo,
      creatorsHere,
      campaignsHere,
      campaignById,
      outreachForCampaign,
      activeCampaignsForCreator,
      summary,
      createCampaign,
      outreachAction,
      regenerateOutreach,
      updateCampaignCreator,
      redeem,
      voidRedemption,
      offerForCode,
      latestBrief,
      briefsHere,
    }),
    [
      state,
      locationMeta,
      toast,
      setRole,
      setLocation,
      notify,
      dismissToast,
      resetDemo,
      creatorsHere,
      campaignsHere,
      campaignById,
      outreachForCampaign,
      activeCampaignsForCreator,
      summary,
      createCampaign,
      outreachAction,
      regenerateOutreach,
      updateCampaignCreator,
      redeem,
      voidRedemption,
      offerForCode,
      latestBrief,
      briefsHere,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useApp(): AppStore {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useApp must be used inside AppStoreProvider");
  return store;
}
