export type CadKind = "freecad" | "solidworks";
export type EmbedMode = "embed" | "dock";
export interface Installation { id: string; kind: CadKind; name: string; path: string }
export interface CadWindow { hwnd: string; pid: number; kind: CadKind; title: string; className: string; dpi: number; awareness: number; nativeMenu: boolean }
export interface Discovery { installations: Installation[]; windows: CadWindow[] }
export interface EmbedState {
  supported: boolean;
  attached: CadWindow | null;
  mode?: EmbedMode | null;
  pendingPids: number[];
  helperPid?: number;
  closing?: boolean;
  shortcut?: boolean;
  error?: string | null;
}
export interface Bounds { x: number; y: number; width: number; height: number; visible: boolean }
export interface EmbedAPI {
  supported: boolean;
  cancelClose(): void;
  status(): Promise<EmbedState>;
  discover(): Promise<Discovery>;
  chooseInstallation(): Promise<Discovery | null>;
  launch(id: string): Promise<{ pid: number }>;
  attach(hwnd: string, pid: number, mode: EmbedMode): Promise<EmbedState>;
  layout(bounds: Bounds): Promise<void>;
  focus(): Promise<EmbedState>;
  detach(): Promise<EmbedState>;
  closeCad(): Promise<EmbedState>;
  diagnose(): Promise<{ path: string }>;
  onEvent(callback: (event: { event: string; state?: EmbedState; message?: string }) => void): () => void;
}
declare global { interface Window { cadEmbed?: EmbedAPI } }
