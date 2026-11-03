// 在 Electron renderer 中读取最终计算颜色，包含透明底色叠加。
function inspectContrast(element) {
  const rgb = (value) => {
    const components = value.match(/[\d.]+/g).map(Number);
    return [...components.slice(0, 3), components[3] ?? 1];
  };
  const blend = (fg, bg) =>
    fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3]));
  const luminance = (color) =>
    color.reduce((sum, value, i) => {
      const x = value / 255;
      return (
        sum +
        (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4) *
          [0.2126, 0.7152, 0.0722][i]
      );
    }, 0);
  const ancestry = [];
  for (let node = element; node; node = node.parentElement)
    ancestry.unshift(node);
  let background = [255, 255, 255];
  for (const node of ancestry)
    background = blend(rgb(getComputedStyle(node).backgroundColor), background);
  const style = getComputedStyle(element);
  const foreground = blend(rgb(style.color), background);
  const a = luminance(foreground),
    b = luminance(background);
  return {
    foreground,
    background,
    ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
    disabled: element.matches(':disabled, [aria-disabled="true"]'),
  };
}
module.exports = { inspectContrast };
