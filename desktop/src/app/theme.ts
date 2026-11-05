import {
  createDarkTheme,
  createLightTheme,
  type BrandVariants,
} from "@fluentui/react-components";
// 石墨 + 信号橙：品牌色只用于主操作、焦点和当前项指示；白底控件文字用 80 级保证对比度。
const brand: BrandVariants = {
  10: "#1a0c04",
  20: "#2e1508",
  30: "#45200c",
  40: "#5a2a10",
  50: "#6f3413",
  60: "#853e16",
  70: "#9c4919",
  80: "#b0521b",
  90: "#c95e20",
  100: "#e06a25",
  110: "#e8742a",
  120: "#ef8a4c",
  130: "#f3a170",
  140: "#f7bb97",
  150: "#fad5bf",
  160: "#fdede3",
};
const typography = {
  fontFamilyBase:
    '"Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", sans-serif',
  fontSizeBase300: "13px",
  lineHeightBase300: "20px",
};
export const lightTheme = { ...createLightTheme(brand), ...typography };
export const darkTheme = {
  ...createDarkTheme(brand),
  ...typography,
  colorNeutralForeground2BrandHover: "#f3a170",
  colorNeutralForeground2BrandPressed: "#f3a170",
  colorNeutralForeground2BrandSelected: "#f3a170",
};
