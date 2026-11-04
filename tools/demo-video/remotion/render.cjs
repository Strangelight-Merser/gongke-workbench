const fs = require("node:fs"),
  path = require("node:path");
const { bundle } = require("@remotion/bundler");
const {
  selectComposition,
  renderMedia,
  renderStill,
} = require("@remotion/renderer");
(async () => {
  const root = path.resolve(__dirname, "../../.."),
    out = path.join(root, "out/demo-video/rebuild/samples"),
    assets = path.join(root, "out/demo-video/rebuild/assets");
  fs.mkdirSync(out, { recursive: true });
  const serveUrl = await bundle({
    entryPoint: path.join(__dirname, "src/index.tsx"),
    publicDir: assets,
    outDir: path.join(root, "out/demo-video/rebuild/bundle"),
  });
  const inputProps = {
    geometry: JSON.parse(fs.readFileSync(path.join(assets, "geometry.json"))),
    recording: JSON.parse(fs.readFileSync(path.join(assets, "recording.json"))),
  };
  const browserExecutable =
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  for (const id of process.argv.slice(2).length
    ? process.argv.slice(2)
    : ["Opening", "Growth", "Styleboard"]) {
    const composition = await selectComposition({
      serveUrl,
      id,
      inputProps,
      browserExecutable,
    });
    const common = {
      composition,
      serveUrl,
      inputProps,
      browserExecutable,
      chromiumOptions: { gl: "angle" },
      timeoutInMilliseconds: 120000,
    };
    if (id === "Styleboard")
      await renderStill({
        ...common,
        output: path.join(out, "styleboard.png"),
      });
    else {
      let last = -1;
      await renderMedia({
        ...common,
        codec: "h264",
        crf: 18,
        pixelFormat: "yuv420p",
        concurrency: 3,
        outputLocation: path.join(out, id.toLowerCase() + ".mp4"),
        onProgress: (p) => {
          const n = Math.floor(p.progress * 10);
          if (n > last) {
            console.log(id, n * 10 + "%");
            last = n;
          }
        },
      });
    }
    console.log(id, "完成");
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
