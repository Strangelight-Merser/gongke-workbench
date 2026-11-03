import type { AgentDiagnostic } from "./diagnostics.cjs";
import type {
  AuthMethod,
  NewSessionResponse,
  RequestPermissionRequest,
  SessionUpdate,
  InitializeResponse,
  PromptResponse,
  RequestPermissionResponse,
} from "@agentclientprotocol/sdk";

export type StdioCommand = {
  command: string;
  args: string[];
  env: Record<string, string>;
};
export type AgentProfile = StdioCommand & { id: string; name: string };
export type AgentSettings = { agents: AgentProfile[]; mcp: StdioCommand };
export type AgentEvent =
  | { type: "update"; update: SessionUpdate }
  | {
      type: "user";
      text: string;
      images?: { path: string; mimeType: string; sha256: string }[];
    }
  | { type: "request"; method: string; params: Record<string, unknown> }
  | { type: "config-result"; configOptions: NonNullable<NewSessionResponse["configOptions"]> }
  | { type: "turn-result"; result: PromptResponse }
  | { type: "permission"; id: string; request: RequestPermissionRequest }
  | {
      type: "permission-resolved";
      id: string;
      outcome: RequestPermissionResponse["outcome"];
    }
  | { type: "notice"; text: string };
export type AgentSnapshot = {
  phase:
    | "disconnected"
    | "starting"
    | "connected"
    | "authenticating"
    | "ready"
    | "prompting"
    | "cancelling";
  project: string;
  agentId: string;
  authMethods: AuthMethod[];
  initialization?: InitializeResponse;
  session?: NewSessionResponse;
  events: AgentEvent[];
  error?: string;
  errorDetails?: AgentDiagnostic;
  stderr?: string;
  stderrLogPath?: string;
};
export type AgentAPI = {
  settings(): Promise<AgentSettings>;
  saveSettings(settings: AgentSettings): Promise<void>;
  state(): Promise<AgentSnapshot>;
  start(agentId: string): Promise<void>;
  authenticate(methodId: string): Promise<void>;
  newSession(): Promise<void>;
  setConfigOption(id: string, value: string): Promise<void>;
  prompt(text: string, referencePaths?: string[]): Promise<void>;
  cancel(): Promise<void>;
  disconnect(): Promise<void>;
  permission(id: string, optionId: string | null): Promise<void>;
  onState(callback: (state: AgentSnapshot) => void): () => void;
};
