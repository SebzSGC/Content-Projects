export type ProjectStage = "CREATED" | "QUEUED" | "RUNNING" | "COMPLETE" | "STALLED";

export type VideoSourcePlatform =
  | "YOUTUBE"
  | "RUMBLE"
  | "TWITCH"
  | "KICK"
  | "ZOOM"
  | "LOOM"
  | "GDRIVE"
  | "DROPBOX"
  | "STREAMYARD"
  | "X"
  | "LOCAL";

export type AspectRatioOption = "9:16" | "16:9" | "1:1" | "4:5";
export type LayoutModeOption = "fill" | "fit" | "split" | "screenshare" | "gameplay";
export type CurationModelType = "ClipAnything" | "ClipBasic" | "Auto" | "SkipClipping";

export type ClipWorkflowSelectType =
  | "agent"
  | "skip-clipping"
  | "dialogue"
  | "auto-asmr"
  | "youtube-trending";

export interface TranscriptWord {
  id: string;
  word: string;
  start: number; // seconds
  end: number;   // seconds
  isFiller?: boolean;
  isPause?: boolean;
  pauseDuration?: number;
  deleted?: boolean;
  highlight?: "none" | "color1" | "color2";
  emoji?: string;
  speaker?: string;
}

export interface BRollSegment {
  id: string;
  type: "ai_video" | "ai_image" | "stock";
  label: string;
  startSec: number;
  endSec: number;
  thumbnailUrl: string;
  creditCost: number;
}

export interface CuratedClip {
  clipId: string;
  projectId: string;
  rank: number;
  title: string;
  viralityScore: number; // 0-99
  scoreBreakdown: {
    hook: string;
    flow: string;
    value: string;
    trend: string;
  };
  viralityExplanation: string;
  duration: number; // seconds
  startSec: number;
  endSec: number;
  aspectRatio: AspectRatioOption;
  layoutMode: LayoutModeOption;
  transcriptWords: TranscriptWord[];
  like: boolean;
  dislike: boolean;
  isEdited: boolean;
  dubProps?: {
    targetLanguage: string;
    voiceClone: boolean;
  };
  hasAutoHook: boolean;
  hookText: string;
  brollSegments: BRollSegment[];
  captionPresetId: string;
  keywords: string[];
  videoUrl?: string;
  thumbnailUrl: string;
  cropX?: number; // 0 to 100 horizontal pan percentage for 9:16 crop (default 50)
  zoom?: number;  // 1 to 2.5 zoom factor (default 1)
}

export interface ClipProject {
  id: string;
  projectId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  stage: ProjectStage;
  progress: number; // 0..1
  etaMinutes?: number;
  sourceInfo: {
    title: string;
    type: VideoSourcePlatform;
    videoId?: string;
    videoUrl: string;
    thumbnailUrl: string;
    durationMs: number;
    resolution: "720p" | "1080p" | "4K";
    language: string;
    fileSizeBytes?: number;
  };
  productTier: "FREE" | "PRO" | "ENTERPRISE";
  clipCount: number;
  demoClipCount?: number;
  demoScrimGradient?: string;
  isDemo?: boolean;
  isLocal?: boolean;
  isPrivate: boolean;
  isFavorite?: boolean;
  storageStatus: "TEMPORARY" | "PERMANENT";
  storageExpireAt: string;
  collectionIds: string[];
  workflowId: string;
  brandTemplateId: string;
  curationPref: {
    model: CurationModelType;
    genre: string;
    clipLengths: string[];
    customPrompt: string;
    keywords: string[];
    rangeStartSec: number;
    rangeEndSec: number;
    skipSlicing: boolean;
  };
  renderPref: {
    enableCaptions: boolean;
    enableAutoHook: boolean;
    enableEmojis: boolean;
    removeFillerWords: boolean;
    removePauses: boolean;
    brollType: "none" | "stock" | "ai_video" | "ai_image";
    enableSpeechEnhance: boolean;
    enableUpscale: boolean;
    upscaleResolution?: "1080p" | "4K";
    dubbingLanguage?: string;
    aspectRatio: AspectRatioOption;
    layoutMode: LayoutModeOption;
  };
  creditsCharged: number;
  creditsFrozen: number;
  refundStatus?: "NONE" | "ELIGIBLE" | "REFUNDED";
}

export interface WorkflowRecipe {
  workflowId: string;
  name: string;
  source: "builtin" | "custom";
  jobType: "clipping" | "editing";
  description: string;
  featured?: boolean;
  isDefault?: boolean;
  coverUrl?: string;
  atomsConfig: {
    outputCount: "many" | "one";
    aspectRatio: AspectRatioOption | "no_change";
    model: CurationModelType;
    captions: boolean;
    autoHeadline: boolean;
    aiEmoji: boolean;
    removeFillerWords: boolean;
    removePauses: boolean;
    aiImageBRoll: boolean;
    aiVideoBRoll: boolean;
    stockBRoll: boolean;
    autoZoom: boolean;
    eyeContact: boolean;
    autoColor: boolean;
    enhanceAudio: boolean;
    autoSfx: boolean;
    translation: boolean;
    dubbing: boolean;
  };
}

export interface BrandTemplate {
  id: string;
  name: string;
  isDefault?: boolean;
  aspectRatio: AspectRatioOption;
  layoutMode: LayoutModeOption;
  captionPreset:
    | "Karaoke Lime"
    | "Hormozi Pop"
    | "Deep Diver"
    | "Marker Sweep"
    | "Bounce Bold"
    | "Minimal Clean";
  animationStyle:
    | "simple-words-pop"
    | "marker-sweep"
    | "breathe-scale-wiggle"
    | "slide-in-from-top"
    | "word-cut"
    | "individual-focus";
  fontFamily: string;
  fontSize: number;
  fontColor: string;
  highlightColor1: string;
  highlightColor2: string;
  strokeColor: string;
  position: "top" | "middle" | "bottom";
  linesPerPage: 1 | 2 | 3;
  uppercase: boolean;
  autoEmoji: boolean;
  watermarkText: string;
  logoOverlayEnabled: boolean;
  autoHookEnabled: boolean;
  brollType: "none" | "stock" | "ai_video";
  removeFillerWords: boolean;
  removePauses: boolean;
}

export interface CreditLedgerEntry {
  id: string;
  timestamp: string;
  projectId?: string;
  description: string;
  type: "GRANT" | "FREEZE" | "SETTLE" | "REFUND" | "TOPUP";
  amount: number;
  balanceAfter: number;
}

export type PlanTier = "FreePlan" | "Starter" | "Pro" | "ProAnnual" | "Enterprise";

export interface CreditWalletState {
  remainingCredit: number; // total settled credits remaining
  frozenCredit: number;    // currently frozen by RUNNING jobs
  totalGrantedCredit: number;
  plan: PlanTier;
  cycle: "Monthly" | "Yearly";
  expireAt: string;
  storageUsedGb: number;
  storageTotalGb: number;
  autoSaveStorage: boolean;
  ledger: CreditLedgerEntry[];
}

export interface AutoImportPlaylist {
  playlistId: string;
  playlistName: string;
  videoCount: number;
  imported: boolean;
  thumbnailUrl: string;
}

export interface AutoImportChannel {
  id: string;
  platform: "YOUTUBE";
  extUserId: string;
  extUserName: string;
  extUserHandle: string;
  extUserPictureLink: string;
  subscriberCount: string;
  active: boolean;
  autoCreateEnabled: boolean; // true = auto_create, false = notify via email
  autoImportScope: "ALL" | "PLAYLIST";
  enableUnlistedVideo: boolean;
  workflowId: string;
  brandKitId: string;
  playlists: AutoImportPlaylist[];
  lastCheckedAt: string;
}

export interface ProjectCollection {
  id: string;
  name: string;
  description: string;
  isPrivate: boolean;
  createdAt: string;
  projectIds: string[];
}

export interface SocialAccountConnection {
  id: string;
  platform: "YOUTUBE" | "TIKTOK" | "INSTAGRAM" | "LINKEDIN" | "X" | "FACEBOOK";
  handle: string;
  displayName: string;
  connected: boolean;
  needsReauth?: boolean;
  followers: string;
}

export interface SocialPostTask {
  id: string;
  clipId: string;
  projectId: string;
  clipTitle: string;
  platforms: ("YOUTUBE" | "TIKTOK" | "INSTAGRAM" | "LINKEDIN" | "X" | "FACEBOOK")[];
  scheduledAt: string;
  status: "SCHEDULED" | "PUBLISHED" | "DRAFT";
  caption: string;
  aspectRatio: AspectRatioOption;
  views: number;
  likes: number;
  shares: number;
}

export interface ClipperCampaign {
  campaignId: string;
  name: string;
  agencyName: string;
  agencyLogoUrl: string;
  thumbnailUrl: string;
  status: "ACTIVE" | "COMPLETED";
  role: "joinable" | "joined" | "owner";
  videoCount: number;
  clippableCount: number;
  duplicableCount: number;
  cpmRateUsd: number;
  budgetRemainingUsd: number;
  budgetTotalUsd: number;
  previewThumbnails: string[];
  brandTemplateId: string;
  description: string;
  sources: {
    sourceId: string;
    title: string;
    durationSec: number;
    videoUrl: string;
    thumbnailUrl: string;
  }[];
}

export interface StatsigGateConfig {
  key: string;
  name: string;
  type: "gate" | "experiment" | "dynamic_config";
  enabled: boolean;
  variant: string;
  description: string;
  moduleId: string;
}

export interface WhatsNewBannerItem {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  tag: "new_features" | "beta" | "announcements" | "programs";
  themeColor: string;
  imageUrl: string;
  ctaText: string;
  ctaRoute: string;
}

export interface MasterTutorialVideo {
  key: string;
  title: string;
  duration: string;
  videoId: string;
  thumbnail: string;
  category: string;
}
