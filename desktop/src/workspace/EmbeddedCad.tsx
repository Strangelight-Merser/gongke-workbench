import { useEffect, useRef, useState, ReactNode } from "react";
import type {
  Discovery,
  EmbedMode,
  EmbedState,
} from "../../electron/embed/types";
import {
  Button,
  Select,
  Menu,
  MenuTrigger,
  MenuPopover,
  MenuList,
  MenuItem,
  MenuDivider,
} from "@fluentui/react-components";
import { MoreHorizontalRegular } from "@fluentui/react-icons";

export function EmbeddedCad({
  visible,
  kind,
  toolbarStart,
  refreshHosts,
  focusRequest,
}: {
  visible: boolean;
  kind: string;
  toolbarStart: ReactNode;
  refreshHosts(): Promise<void>;
  focusRequest: number;
}) {
  const api = window.cadEmbed;
  const area = useRef<HTMLDivElement>(null);
  const focusButton = useRef<HTMLButtonElement>(null);
  const focusedRequest = useRef(0);
  const [found, setFound] = useState<Discovery>({
    installations: [],
    windows: [],
  });
  const [state, setState] = useState<EmbedState>({
    supported: !!api?.supported,
    attached: null,
    pendingPids: [],
  });
  const [installation, setInstallation] = useState("");
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<EmbedMode>("embed");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (error) {
      setMessage(
        String(error).replace(
          /^Error invoking remote method '[^']+': Error: /,
          "",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    if (!api?.supported) return;
    const [found, status] = await Promise.all([api.discover(), api.status()]);
    setFound(found);
    setState(status);
  }
  useEffect(() => {
    if (visible) void run(refresh);
  }, [visible, kind]);
  useEffect(
    () =>
      api?.onEvent((event) => {
        if (event.state) setState(event.state);
        if (event.message) setMessage(event.message);
        if (event.event === "closing") setClosing(true);
        if (event.event === "returnFocus") focusButton.current?.focus();
      }),
    [api],
  );
  useEffect(() => {
    if (!api?.supported || !area.current) return;
    const element = area.current;
    let frame = 0,
      active = true;
    const update = () => {
      const r = element.getBoundingClientRect();
      // 原生窗口在 Chromium 之上，HTML 模态层出现时必须腾出这个区域。
      const modal = !!document.querySelector(
        'dialog[open], [role="dialog"][aria-modal="true"], .modal-backdrop, .modal-scrim, [role="menu"]',
      );
      void api
        .layout({
          x: r.x,
          y: r.y,
          width: r.width,
          height: r.height,
          visible: visible && !modal && document.visibilityState === "visible",
        })
        .catch((error) => {
          if (active) setMessage(String(error));
        });
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const resize = new ResizeObserver(schedule);
    resize.observe(element);
    const mutation = new MutationObserver(schedule);
    mutation.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["open", "aria-modal", "class"],
    });
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    document.addEventListener("visibilitychange", schedule);
    schedule();
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      resize.disconnect();
      mutation.disconnect();
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      document.removeEventListener("visibilitychange", schedule);
      void api
        .layout({ x: 0, y: 0, width: 0, height: 0, visible: false })
        .catch(() => {});
    };
  }, [api, visible, state.attached?.hwnd]);
  useEffect(() => {
    if (
      focusRequest > focusedRequest.current &&
      visible &&
      state.attached?.kind === kind
    ) {
      focusedRequest.current = focusRequest;
      void run(async () => {
        setState(await api!.focus());
      });
    }
  }, [focusRequest, visible, state.attached?.hwnd, kind]);
  const supported = !!api?.supported && kind !== "autocad";
  const installs = found.installations.filter((i) => i.kind === kind);
  const windows = found.windows.filter((w) => w.kind === kind);
  const installId = installs.some((i) => i.id === installation)
    ? installation
    : installs[0]?.id || "";
  const hwnd = windows.some((w) => w.hwnd === selected)
    ? selected
    : windows[0]?.hwnd || "";
  return (
    <>
      <div className="toolbar cad-toolbar" aria-label="CAD 工具栏">
        {toolbarStart}
        {supported && state.attached?.kind === kind && (
          <Button
            size="small"
            ref={focusButton}
            disabled={busy}
            onClick={() =>
              run(async () => {
                setState(await api!.focus());
              })
            }
          >
            进入 CAD
          </Button>
        )}
        <span className="toolbar-space" />
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button
              size="small"
              appearance="subtle"
              icon={<MoreHorizontalRegular />}
              aria-label="CAD 更多操作"
            />
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              <MenuItem
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await refresh();
                    await refreshHosts();
                  })
                }
              >
                重新检测连接
              </MenuItem>
              {supported && (
                <>
                  <MenuItem
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const result = await api!.chooseInstallation();
                        if (result) setFound(result);
                      })
                    }
                  >
                    选择 CAD 程序
                  </MenuItem>
                  <MenuItem
                    disabled={busy || !state.attached}
                    onClick={() =>
                      run(async () => {
                        setState(await api!.detach());
                        await refresh();
                      })
                    }
                  >
                    在独立窗口中编辑
                  </MenuItem>
                  <MenuItem
                    disabled={busy || !state.attached}
                    onClick={() =>
                      run(async () => {
                        setState(await api!.closeCad());
                        await refresh();
                      })
                    }
                  >
                    关闭 CAD
                  </MenuItem>
                  <MenuDivider />
                  <MenuItem
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const result = await api!.diagnose();
                        setMessage(`诊断已保存：${result.path}`);
                      })
                    }
                  >
                    导出连接诊断
                  </MenuItem>
                </>
              )}
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>
      {closing && (
        <div className="cad-message" role="status">
          <span>请完成 CAD 保存并关闭窗口</span>
          <Button
            onClick={() => {
              api!.cancelClose();
              setClosing(false);
            }}
          >
            取消退出
          </Button>
        </div>
      )}
      {(message || state.error) && (
        <div className="cad-message" role="status">
          {message || state.error}
        </div>
      )}
      {supported && (
        <section
          className="cad-editor"
          hidden={!visible}
          aria-label="CAD 编辑区"
        >
          {state.attached && state.attached.kind !== kind && (
            <div className="cad-message">
              先在“CAD 更多操作”中释放当前窗口，再切换编辑环境。
            </div>
          )}
          {!state.attached && (
            <div className="cad-connect">
              <h3>连接 {kind === "freecad" ? "FreeCAD" : "SOLIDWORKS"}</h3>
              <div>
                <Select
                  aria-label="CAD 安装"
                  value={installId}
                  onChange={(e) => setInstallation(e.target.value)}
                >
                  {!installs.length && <option value="">未检测到安装</option>}
                  {installs.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </Select>
                <Button
                  disabled={busy || !installId}
                  onClick={() =>
                    run(async () => {
                      await api!.launch(installId);
                      setMessage("CAD 启动后，在下方选择它的主窗口。");
                      await refresh();
                    })
                  }
                >
                  启动 CAD
                </Button>
              </div>
              <div>
                <Select
                  aria-label="CAD 主窗口"
                  value={hwnd}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {!windows.length && <option value="">等待 CAD 主窗口</option>}
                  {windows.map((w) => (
                    <option key={w.hwnd} value={w.hwnd}>
                      {w.title}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="窗口模式"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as EmbedMode)}
                >
                  <option value="embed">嵌入窗口</option>
                  <option value="dock">自动停靠</option>
                </Select>
                <Button disabled={busy} onClick={() => run(refresh)}>
                  重新检测
                </Button>
                <Button
                  appearance="primary"
                  disabled={busy || !hwnd}
                  onClick={() =>
                    run(async () => {
                      const target = windows.find((w) => w.hwnd === hwnd)!;
                      api!.cancelClose();
                      setClosing(false);
                      setState(
                        await api!.attach(target.hwnd, target.pid, mode),
                      );
                    })
                  }
                >
                  进入建模
                </Button>
              </div>
            </div>
          )}
          <div
            ref={area}
            className="cad-surface"
            tabIndex={0}
            aria-label="原生建模窗口"
            onFocus={() => {
              if (state.attached)
                void api!.focus().catch((e) => setMessage(String(e)));
            }}
          >
            {!state.attached && <p>连接 CAD 后，模型和特征树会显示在这里。</p>}
          </div>
        </section>
      )}
    </>
  );
}
