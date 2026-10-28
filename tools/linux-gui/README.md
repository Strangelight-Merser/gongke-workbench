# Linux 原生界面验收

在 ARM64 Docker 中运行官方 FreeCAD 1.1.4、已打包的工作台和一个独立工程副本。浏览器中的 noVNC 提供真实桌面的鼠标与键盘输入；不以脚本改尺寸代替草图编辑。

构建目录需要本目录的 `Dockerfile`、`start.sh`、`bootstrap.FCMacro`，以及以下文件：

- `FreeCAD.AppImage`：[官方 Linux aarch64 1.1.4](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4)，SHA256 为 `675d1a4295b2183e0e1d816a4b5557dcb63aeced4e60aaa28d6c3686f4c71dc9`。
- `GongKeWorkbench.zip`：独立安装包，ZIP 顶层须为 `GongKeWorkbench/`。可先用 `tools/install_freecad_workbench.py --mod-dir /absolute/staging/Mod` 生成目录，再把其中的 `GongKeWorkbench/` 压缩；安装脚本本身不生成 ZIP。

先将待测 FCStd **复制**为独立运行目录中的 `ui_shaft.FCStd`。不要挂载日常工程或用户主目录。

```sh
docker build -t gongke-freecad-ui:1.1.4 /absolute/build-directory
docker run -d --name gongke-native-linux-ui-v1 --init --cpus=4 --memory=6g \
  -p 127.0.0.1::6080 \
  --mount type=bind,src=/absolute/runtime-directory,dst=/workspace \
  gongke-freecad-ui:1.1.4
docker port gongke-native-linux-ui-v1 6080
```

打开输出端口的 `http://127.0.0.1:PORT/vnc.html?autoconnect=1&resize=scale`。VNC 仅监听容器回环地址，宿主机仅发布回环地址上的网页端口。日志写入运行目录的 `logs/`，启动信息写入 `bootstrap.json`。

MCP 客户端使用以下 stdio 命令；桥接 HTTP 和凭据留在容器内：

```sh
docker exec -i gongke-native-linux-ui-v1 python3 -P -m gongke_core mcp
```

验收完成后先在 FreeCAD 中保存并退出；退出会关闭该容器的桌面子进程。需要中止时执行 `docker stop gongke-native-linux-ui-v1`。工程副本与日志保存在宿主机。此环境验证 Linux 功能路径，不证明 macOS 崩溃已修复，也不替代真实学生试用或 SOLIDWORKS 实机验收。
