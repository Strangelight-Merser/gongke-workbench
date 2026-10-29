export type Data = Record<string, any>;
declare global {
  interface Window {
    gongke: {
      request: (method: string, params?: Data) => Promise<any>;
      chooseProject: (create: boolean) => Promise<string | null>;
      configure: (settings: Data) => Promise<Data>;
      settings: () => Promise<Data>;
      restart: () => Promise<Data>;
      reveal: (path: string) => Promise<void>;
      onEvent: (callback: (event: Data) => void) => () => void;
    };
  }
}
export const call = (method: string, params: Data = {}) =>
  window.gongke.request(method, params);
export const text = (value: any) => JSON.stringify(value, null, 2);
export const errorText = (error: unknown) =>
  String(error instanceof Error ? error.message : error).replace(
    /^Error invoking remote method '[^']+': Error: /,
    "",
  );
