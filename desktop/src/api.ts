import type { OnboardingAPI } from "../electron/onboarding/types.cjs";
import type { AgentAPI } from "../electron/acp/types.cjs";
export type Data = Record<string, any>;
declare global {
  interface Window {
    gongke: {
      platform: string;
      request: (method: string, params?: Data) => Promise<any>;
      chooseProject: (create: boolean) => Promise<string | null>;
      agent: AgentAPI;
      documents: {
        import(): Promise<import("./project/types").ProjectFile[]>;
        read(path: string): Promise<{ mime: string; content: string }>;
      };
      getAgentMode(): Promise<"model" | "practice">;
      setAgentMode(mode: "model" | "practice"): Promise<void>;
      onboarding: OnboardingAPI;
      restart: () => Promise<Data>;
      reveal: (path: string) => Promise<void>;
      onEvent: (callback: (event: Data) => void) => () => void;
    };
  }
}
export const call = (method: string, params: Data = {}) =>
  window.gongke.request(method, params);
export const errorText = (error: unknown) =>
  String(error instanceof Error ? error.message : error).replace(
    /^Error invoking remote method '[^']+': Error: /,
    "",
  );
