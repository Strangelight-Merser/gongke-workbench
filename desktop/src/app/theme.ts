import { webDarkTheme, webLightTheme } from "@fluentui/react-components";
const typography = {
  fontFamilyBase:
    '"Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", sans-serif',
  fontSizeBase300: "13px",
  lineHeightBase300: "20px",
};
export const lightTheme = { ...webLightTheme, ...typography };
export const darkTheme = {
  ...webDarkTheme,
  ...typography,
  // 与 tokens.css 的深色强调色一致；默认品牌悬停色在 #383838 上只有 4.18:1。
  colorNeutralForeground2BrandHover: "#75b6ed",
  colorNeutralForeground2BrandPressed: "#75b6ed",
  colorNeutralForeground2BrandSelected: "#75b6ed",
};
