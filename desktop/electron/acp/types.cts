import type {
  AuthMethod,
  NewSessionResponse,
  RequestPermissionRequest,
  SessionUpdate,
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
  | { type: "user"; text: string }
  | { type: "permission"; id: string; request: RequestPermissionRequest }
  | { type: "permission-resolved"; id: string }
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
  session?: NewSessionResponse;
  events: AgentEvent[];
  error?: string;
};
export type AgentAPI = {
  settings(): Promise<AgentSettings>;
  saveSettings(settings: AgentSettings): Promise<void>;
  state(): Promise<AgentSnapshot>;
  start(agentId: string): Promise<void>;
  authenticate(methodId: string): Promise<void>;
  newSession(): Promise<void>;
  prompt(text: string): Promise<void>;
  cancel(): Promise<void>;
  disconnect(): Promise<void>;
  permission(id: string, optionId: string | null): Promise<void>;
  onState(callback: (state: AgentSnapshot) => void): () => void;
};
