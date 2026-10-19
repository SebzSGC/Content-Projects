import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import {
  AspectRatioOption,
  AutoImportChannel,
  BrandTemplate,
  ClipperCampaign,
  ClipProject,
  CreditWalletState,
  CuratedClip,
   CurationModelType,
  LayoutModeOption,
  PlanTier,
  ProjectCollection,
  SocialAccountConnection,
  SocialPostTask,
  StatsigGateConfig,
  VideoSourcePlatform,
  WorkflowRecipe,
} from "@/types/opus";
import {
  INITIAL_AUTO_IMPORT_CHANNELS,
  INITIAL_BRAND_TEMPLATES,
  INITIAL_CAMPAIGNS,
  INITIAL_CLIPS,
  INITIAL_COLLECTIONS,
  INITIAL_CREDIT_WALLET,
  INITIAL_PROJECTS,
  INITIAL_SOCIAL_ACCOUNTS,
  INITIAL_SOCIAL_POSTS,
  INITIAL_STATSIG_GATES,
  INITIAL_WORKFLOW_RECIPES,
} from "@/data/seedData";
import { CpuBenchmarkResult } from "@/lib/cpuBenchmark";

// ============================================================================
// 1. EXACT REA MATHEMATICAL FORMULAS (Modules 286660, 277924, 612196)
// ============================================================================

export function calculateClipRangeDuration(startSec: number, endSec: number): number {
  return Math.max(0, Math.round(endSec - startSec));
}

/**
 * 1 credit = 1 minute of video processed, rounded up via Math.ceil
 */
export function calculateBaseClippingCredits(durationSec: number): number {
  const d = Math.max(0, durationSec);
  if (d === 0) return 0;
  return Math.max(1, Math.ceil(d / 60));
}

/**
 * Module 277924: 1 credit per 10 seconds (6 credits/min).
 * Exemption: 0 extra credits if plan === 'ProAnnual' && durationSec < 1800 && resolution === '720p' && proGateEnabled
 */
export function calculateUpscaleCredits(
  durationSec: number,
  plan: PlanTier,
  sourceResolution: "720p" | "1080p" | "4K",
  proExemptionGateEnabled = true,
  targetResolution: "1080p" | "4K" = "1080p"
): { credits: number; exempted: boolean } {
  if (durationSec <= 0) return { credits: 0, exempted: false };
  if (
    proExemptionGateEnabled &&
    plan === "ProAnnual" &&
    durationSec < 1800 &&
    sourceResolution === "720p" &&
    targetResolution === "1080p"
  ) {
    return { credits: 0, exempted: true };
  }
  const baseUpscale = Math.max(1, Math.floor(durationSec / 10));
  return {
    credits: targetResolution === "4K" ? Math.round(baseUpscale * 1.5) : baseUpscale,
    exempted: false,
  };
}

/**
 * Speech Enhancement surcharge: 3 credits per minute
 */
export function calculateSpeechEnhanceCredits(
  durationSec: number,
  enabled: boolean
): number {
  if (!enabled || durationSec <= 0) return 0;
  return Math.ceil(durationSec / 60) * 3;
}

/**
 * Generative AI Video B-Roll surcharge: 2 credits per minute
 */
export function calculateBrollCredits(
  durationSec: number,
  brollType: "none" | "stock" | "ai_video" | "ai_image"
): number {
  if (durationSec <= 0) return 0;
  if (brollType === "ai_video") return Math.ceil(durationSec / 60) * 2;
  if (brollType === "ai_image") return Math.ceil(durationSec / 60) * 1;
  return 0;
}

/**
 * AI Voice Dubbing surcharge: 5 credits per minute
 */
export function calculateDubbingCredits(
  durationSec: number,
  dubbingEnabled: boolean
): number {
  if (!dubbingEnabled || durationSec <= 0) return 0;
  return Math.ceil(durationSec / 60) * 5;
}

// ============================================================================
// 2. PERSISTED JOTAI ATOMS (Replicating OpusClip's 161-Atom Reactive Graph)
// ============================================================================

export const themeModeAtom = atomWithStorage<"dark" | "light">(
  "clippers.themeMode",
  "light"
);

export const sidebarExpandedAtom = atomWithStorage<boolean>(
  "clippers.sidebarExpanded",
  true
);

export const dashboardAudienceModeAtom = atomWithStorage<"existing-user" | "new-user">(
  "clippers.dashboardAudienceMode",
  "existing-user"
);

export const statsigGatesAtom = atomWithStorage<StatsigGateConfig[]>(
  "clippers.statsigGates",
  INITIAL_STATSIG_GATES
);

export const creditWalletAtom = atomWithStorage<CreditWalletState>(
  "clippers.creditWallet",
  INITIAL_CREDIT_WALLET
);

export const availableCreditAtom = atom((get) => {
  const wallet = get(creditWalletAtom);
  return Math.max(0, wallet.remainingCredit - wallet.frozenCredit);
});

export const projectsAtom = atomWithStorage<ClipProject[]>(
  "clippers.projects",
  INITIAL_PROJECTS
);

export const clipsAtom = atomWithStorage<CuratedClip[]>(
  "clippers.clips",
  INITIAL_CLIPS
);

export const workflowRecipesAtom = atomWithStorage<WorkflowRecipe[]>(
  "clippers.workflowRecipes",
  INITIAL_WORKFLOW_RECIPES
);

export const selectedWorkflowIdAtom = atomWithStorage<string>(
  "clippers.selectedWorkflowId",
  "builtin:long-to-shorts"
);

export const brandTemplatesAtom = atomWithStorage<BrandTemplate[]>(
  "clippers.brandTemplates",
  INITIAL_BRAND_TEMPLATES
);

export const selectedBrandTemplateIdAtom = atomWithStorage<string>(
  "clippers.selectedBrandTemplateId",
  "preset-karaoke-lime"
);

export const collectionsAtom = atomWithStorage<ProjectCollection[]>(
  "clippers.collections",
  INITIAL_COLLECTIONS
);

export const autoImportChannelsAtom = atomWithStorage<AutoImportChannel[]>(
  "clippers.autoImportChannels",
  INITIAL_AUTO_IMPORT_CHANNELS
);

export const socialAccountsAtom = atomWithStorage<SocialAccountConnection[]>(
  "clippers.socialAccounts",
  INITIAL_SOCIAL_ACCOUNTS
);

export const socialPostsAtom = atomWithStorage<SocialPostTask[]>(
  "clippers.socialPosts",
  INITIAL_SOCIAL_POSTS
);

export const campaignsAtom = atomWithStorage<ClipperCampaign[]>(
  "clippers.campaigns",
  INITIAL_CAMPAIGNS
);

export const cpuBenchmarkAtom = atom<CpuBenchmarkResult | null>(null);

// Active Modal Registry (Module 492442 popupQueueStore)
export type ActiveModalType =
  | "none"
  | "search"
  | "auto-import"
  | "upscale"
  | "social-accounts"
  | "pricing"
  | "manage-recipes"
  | "api-access"
  | "affiliate"
  | "campaign-invite"
  | "tutorial-video"
  | "ai-connect";

export const activeModalAtom = atom<ActiveModalType>("none");
export const activeTutorialVideoIdAtom = atom<string>("82BNJZrBCB4");

export interface AiConfigState {
  provider: "gemini" | "groq" | "openai";
  apiKey: string;
  isConnected: boolean;
  model: string;
  lastChecked?: string;
}

export const aiConfigAtom = atomWithStorage<AiConfigState>(
  "clippers.aiConfig",
  {
    provider: "gemini",
    apiKey: "",
    isConnected: false,
    model: "gemini-3.8-flash",
  }
);

// Preflight / Draft Submission State (Module 311846 submitStore)
export interface DraftSubmissionState {
  sourceUrl: string;
  title: string;
  author?: string;
  platform: VideoSourcePlatform;
  durationSec: number;
  resolution: "720p" | "1080p" | "4K";
  thumbnailUrl: string;
  localObjectUrl?: string;
  fileSizeBytes?: number;
  autoEditMode: boolean; // false = Clip long video, true = Auto-edit footage
  workflowId: string;
  brandTemplateId: string;
  model: CurationModelType;
  genre: string;
  clipLengths: string[];
  customPrompt: string;
  keywords: string[];
  rangeStartSec: number;
  rangeEndSec: number;
  enableCaptions: boolean;
  enableAutoHook: boolean;
  enableEmojis: boolean;
  removeFillerWords: boolean;
  removePauses: boolean;
  brollType: "none" | "stock" | "ai_video" | "ai_image";
  enableSpeechEnhance: boolean;
  enableUpscale: boolean;
  upscaleResolution: "1080p" | "4K";
  enableDubbing: boolean;
  dubbingLanguage: string;
  aspectRatio: AspectRatioOption;
  layoutMode: LayoutModeOption;
  isPrivate: boolean;
}

export const DEFAULT_DRAFT_SUBMISSION: DraftSubmissionState = {
  sourceUrl: "",
  title: "",
  platform: "YOUTUBE",
  durationSec: 1200, // 20 mins default preflight
  resolution: "1080p",
  thumbnailUrl: "https://i.ytimg.com/vi_webp/TndWQw05wsA/maxresdefault.webp",
  autoEditMode: false,
  workflowId: "builtin:long-to-shorts",
  brandTemplateId: "preset-karaoke-lime",
  model: "ClipAnything",
  genre: "Auto",
  clipLengths: ["Auto (<90s)", "30s~59s"],
  customPrompt: "",
  keywords: [],
  rangeStartSec: 0,
  rangeEndSec: 1200,
  enableCaptions: true,
  enableAutoHook: true,
  enableEmojis: true,
  removeFillerWords: true,
  removePauses: true,
  brollType: "stock",
  enableSpeechEnhance: false,
  enableUpscale: false,
  upscaleResolution: "1080p",
  enableDubbing: false,
  dubbingLanguage: "es",
  aspectRatio: "9:16",
  layoutMode: "fill",
  isPrivate: false,
};

export const draftSubmissionAtom = atomWithStorage<DraftSubmissionState>(
  "clippers.draftSubmission",
  DEFAULT_DRAFT_SUBMISSION
);
