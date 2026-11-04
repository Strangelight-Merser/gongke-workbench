export type Layout = {
  tree: number;
  agent: number;
  treeOpen: boolean;
  agentOpen: boolean;
  dark: boolean;
};
export const defaultLayout: Layout = {
  tree: 232,
  agent: 352,
  treeOpen: true,
  agentOpen: true,
  dark: false,
};
export function panelWidth(value: number, panel: "tree" | "agent") {
  return Math.max(
    panel === "tree" ? 180 : 300,
    Math.min(panel === "tree" ? 360 : 520, value),
  );
}
// 窄窗口保留中心编辑空间，用户再次展开时立即生效。
export function fitLayout(layout: Layout, width: number): Layout {
  return width -
    48 -
    10 -
    (layout.treeOpen ? layout.tree : 0) -
    (layout.agentOpen ? layout.agent : 0) <
    640
    ? { ...layout, treeOpen: false }
    : layout;
}
