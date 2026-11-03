import { useEffect, useRef, useState } from "react";
import type { Discovery, EmbedMode, EmbedState } from "./types";
import "./embed.css";

export function EmbeddedCad({ visible, kind }: { visible: boolean; kind: string }) {
  const api = window.cadEmbed;
  const area = useRef<HTMLDivElement>(null);
  const focusButton = useRef<HTMLButtonElement>(null);
  const [found, setFound] = useState<Discovery>({ installations: [], windows: [] });
  const [state, setState] = useState<EmbedState>({ supported: !!api?.supported, attached: null, pendingPids: [] });
  const [installation, setInstallation] = useState("");
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<EmbedMode>("embed");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  async function run(action: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await action(); } catch (error) { setMessage(String(error).replace(/^Error invoking remote method '[^']+': Error: /, "")); }
    finally { setBusy(false); }
  }
  async function refresh() {
    if (!api?.supported) return;
    const [found, status] = await Promise.all([api.discover(), api.status()]);
    setFound(found); setState(status);
  }
  useEffect(() => { if (visible) void run(refresh); }, [visible, kind]);
  useEffect(() => api?.onEvent((event) => {
    if (event.state) setState(event.state);
    if (event.message) setMessage(event.message);
    if (event.event === "closing") setClosing(true);
    if (event.event === "returnFocus") focusButton.current?.focus();
  }), [api]);
  useEffect(() => {
    if (!api?.supported || !area.current) return;
    const element = area.current;
    let frame = 0, active = true;
    const update = () => {
      const r = element.getBoundingClientRect();
      // 原生窗口在 Chromium 之上，HTML 模态层出现时必须腾出这个区域。
      const modal = !!document.querySelector('dialog[open], [role="dialog"][aria-modal="true"], .modal-backdrop, .modal-scrim');
      void api.layout({ x: r.x, y: r.y, width: r.width, height: r.height, visible: visible && !modal && document.visibilityState === "visible" })
        .catch(error => { if (active) setMessage(String(error)); });
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update); };
    const resize = new ResizeObserver(schedule); resize.observe(element);
    const mutation = new MutationObserver(schedule); mutation.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["open", "aria-modal", "class"] });
    window.addEventListener("resize", schedule); window.addEventListener("scroll", schedule, true);
    document.addEventListener("visibilitychange", schedule);
    schedule();
    return () => {
      active = false; cancelAnimationFrame(frame); resize.disconnect(); mutation.disconnect();
      window.removeEventListener("resize", schedule); window.removeEventListener("scroll", schedule, true);
      document.removeEventListener("visibilitychange", schedule);
      void api.layout({ x: 0, y: 0, width: 0, height: 0, visible: false }).catch(() => {});
    };
  }, [api, visible, state.attached?.hwnd]);
  if (!api?.supported) return null;
  const installs = found.installations.filter(i => i.kind === kind);
  const windows = found.windows.filter(w => w.kind === kind);
  const installId = installs.some(i => i.id === installation) ? installation : installs[0]?.id || "";
  const hwnd = windows.some(w => w.hwnd === selected) ? selected : windows[0]?.hwnd || "";
  return <>
    {closing && <div className="toolbar" role="status">
      <span>请完成 CAD 保存并关闭窗口</span>
      <button onClick={() => { api.cancelClose(); setClosing(false); }}>取消退出</button>
    </div>}
    <section className="cad-editor" style={{ display: visible ? "flex" : "none" }} aria-label="CAD 编辑区">
      <div className="toolbar cad-controls">
        {!state.attached ? <>
          <select aria-label="CAD 安装" value={installId} onChange={e => setInstallation(e.target.value)}>
            {!installs.length && <option value="">未检测到安装</option>}
            {installs.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          <button disabled={busy || !installId} onClick={() => run(async () => {
            const result = await api.launch(installId); setMessage(`已启动，进程 ${result.pid}；主窗口出现后刷新窗口列表。`);
          })}>启动</button>
          <button disabled={busy} onClick={() => run(async () => { const result = await api.chooseInstallation(); if (result) setFound(result); })}>选择程序</button>
          <button disabled={busy} onClick={() => run(refresh)}>刷新窗口</button>
          <select aria-label="CAD 主窗口" value={hwnd} onChange={e => setSelected(e.target.value)}>
            {!windows.length && <option value="">等待 CAD 主窗口</option>}
            {windows.map(w => <option key={w.hwnd} value={w.hwnd}>{w.title} · PID {w.pid}</option>)}
          </select>
          <select aria-label="窗口模式" value={mode} onChange={e => setMode(e.target.value as EmbedMode)}>
            <option value="embed">嵌入</option><option value="dock">自动停靠</option>
          </select>
          <button disabled={busy || !hwnd} onClick={() => run(async () => {
            const target = windows.find(w => w.hwnd === hwnd)!;
            api.cancelClose(); setClosing(false);
            setState(await api.attach(target.hwnd, target.pid, mode));
          })}>进入建模</button>
        </> : <>
          <span>{state.attached.kind === "freecad" ? "FreeCAD" : "SOLIDWORKS"} · {state.mode === "embed" ? "嵌入" : "自动停靠"}</span>
          <button ref={focusButton} onClick={() => run(async () => { setState(await api.focus()); })}>进入 CAD</button>
          <button disabled={busy} onClick={() => run(async () => { setState(await api.detach()); await refresh(); })}>独立窗口</button>
          <button disabled={busy} onClick={() => run(async () => { setState(await api.closeCad()); await refresh(); })}>关闭 CAD</button>
        </>}
        <button disabled={busy} onClick={() => run(async () => { const result = await api.diagnose(); setMessage(`诊断已保存：${result.path}`); })}>保存诊断</button>
      </div>
      {(message || state.error) && <div className="cad-message" role="status">{message || state.error}</div>}
      {state.attached && state.attached.kind !== kind && <div className="cad-message">先释放或关闭当前 CAD，再切换编辑环境。</div>}
      <div ref={area} className="cad-surface" tabIndex={0} aria-label="原生建模窗口" onFocus={() => { if (state.attached) void api.focus().catch(e => setMessage(String(e))); }}>
        {!state.attached && <p>选择 CAD 主窗口，开始草图、特征和装配建模。</p>}
      </div>
    </section>
  </>;
}
