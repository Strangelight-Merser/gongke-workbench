import type { AgentDiagnostic } from "../acp/diagnostics.cjs";
export type Provider = "deepseek" | "workbuddy";
export type Step =
  | "detect"
  | "install"
  | "account"
  | "credentials"
  | "connect"
  | "verify"
  | "complete";
export type Release = {
  provider: Provider;
  version: string;
  url: string;
  size: number;
  sha512: string;
  signerThumbprint: string;
};
export type Progress = {
  step: Step;
  command?: string;
  application?: string;
  version?: string;
  project?: string;
  configuredAt?: string;
  verifiedAt?: string;
  evidence?: string;
  serviceName?: string;
  configPath?: string;
  backupPath?: string;
  conflicts?: { name: string; reason: string; path: string }[];
};
export type OnboardingState = {
  selected: Provider;
  agents: Record<Provider, Progress>;
  working?: boolean;
  installing?: {
    provider: Provider;
    phase: string;
    received: number;
    total: number;
  };
  error?: string;
  errorDetails?: AgentDiagnostic;
  releases: Release[];
  canInstall: boolean;
};
export type Link = "register" | "balance" | "keys" | "help" | "workbuddy";
export type OnboardingAction =
  | { type: "detect" }
  | { type: "select"; provider: Provider }
  | { type: "locate" }
  | { type: "install"; consent: true }
  | { type: "cancel-install" }
  | { type: "link"; link: Link }
  | { type: "advance"; step: "account" | "credentials" | "connect" }
  | { type: "open-agent" }
  | { type: "connect"; confirmUserConfig?: boolean }
  | { type: "verify" }
  | { type: "confirm-workbuddy"; taskId: string; sawReply: true };
export type OnboardingAPI = {
  state(): Promise<OnboardingState>;
  act(action: OnboardingAction): Promise<OnboardingState>;
  onState(callback: (state: OnboardingState) => void): () => void;
};
