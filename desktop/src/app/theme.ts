import {
  createDarkTheme,
  createLightTheme,
  type BrandVariants,
} from "@fluentui/react-components";
// 与 Logo 同一青绿色相；控件文字使用更深的色阶保证白底对比度。
const brand: BrandVariants = {
  10: "#02130f",
  20: "#06271f",
  30: "#093c30",
  40: "#0b493b",
  50: "#0d574a",
  60: "#0f6353",
  70: "#106e5d",
  80: "#147d69",
  90: "#168b75",
  100: "#1aa088",
  110: "#24b69c",
  120: "#54cbb7",
  130: "#79d7c7",
  140: "#a2e4d8",
  150: "#c9eee5",
  160: "#e4f5ef",
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
  colorNeutralForeground2BrandHover: "#79d7c7",
  colorNeutralForeground2BrandPressed: "#79d7c7",
  colorNeutralForeground2BrandSelected: "#79d7c7",
};
