# Desktop CI 第二轮：启动证据

失败基线：`b589c162f079ec7cf7c215d91251b11c7a7c2dda`，run `41771770952`。macOS 三个服务子进程在 15 秒内没有 stdout/stderr；其中一个拒绝导入 numpy/scipy/OCP/build123d 仍超时，所以上轮数值库预加载归因不成立。现有日志无法区分导入、锁、HTTP 服务器启动、输入等待，不据此改动产品路径。

## 本次临时诊断

此诊断单独提交，定位并回归验证后删除 `startup_trace.py`、service 中 trace 调用、诊断工具和 workflow 诊断步骤。

- 原来的三个测试和 15 秒超时不变；仅测试步骤设置 `GONGKE_STARTUP_TRACE_DIR`。
- 每个服务 PID 单独写文件，记录单调时间与固定阶段名，不记录请求、令牌、环境变量或局部变量。从应用依赖导入前开始，每 5 秒 faulthandler 输出所有线程栈，能在 15 秒 kill 之前留下证据。
- 阶段涵盖 commands/tools/hosts/project/tasks 导入、stdio 重配置、私有输入、参数、InstanceLock、Application、ConnectionServer 导入和启动、stdin 行、dispatch、输出 flush 和关闭。
- 原测试之后，无论成功或失败，macOS 补跑 `tools/diagnose_service_startup.py`：在 runpy 导入应用之前启用栈转储，并保存 `-X importtime` 的 stderr、JSONL stdout 和结果。探针也用 15 秒上限，不用于替代原测试，不预热原测试。
- 随后以 `always()` 上传 `service-startup-macOS-<sha>` / `service-startup-Windows-<sha>`。仅上传日志、probe/result.json 与探针 stdout，不上传 state/service.json、数据库或工程目录。后续构建步骤仍受原测试成功条件限制，没有 continue-on-error。

## 下一轮读取方式

先看 `tests/service-<pid>.log` 的最后阶段及 5/10 秒线程栈；再对照 `probe/imports.log`、`probe/early-stack.log`、`probe/service-<pid>.log` 和 `probe/result.json`。

| 最后阶段或栈 | 下一步定位 |
|---|---|
| 缺少 service.module.enter | 查看 early-stack/importtime，核对解释器和包加载 |
| imports.*.begin | 根据线程栈定位具体模块/导入调用 |
| instance_lock.begin | 定位文件打开/系统锁，检查实际 state_dir 与其他实例 |
| application.begin | 线程栈区分 SQLite、schema、宿主初始化 |
| connection.start.begin | 区分 HTTPServer.server_bind 内的 socket bind、getfqdn 名称解析以及服务线程启动；目前这些都是待证假设 |
| stdin.wait | 查看输入读取栈和原测试提供的换行/EOF，不能只凭零输出推断缓冲 |
| response.flushed / shutdown.begin | 区分“尚未响应”和“已响应但退出卡住”，检查 server.shutdown/tasks.close |

本机正常探针约 0.62 秒完成，首个响应约 0.063 秒，退出约 0.565 秒；仅代表本机。另用临时注入的慢 getfqdn 验证：在父进程第 7 秒终止子进程前，日志已留下 connection.start.begin 和第 5 秒 server_bind 全线程栈。该注入只验证诊断有效，**不证明 CI 正卡在 getfqdn**。

Windows 信号失败的根因和修正契约另见 [退出契约](process-exit-contract.md)。窗口关闭与强制结束进程不能等同；本次未新增 Job Object 或原生控制台关闭处理器。

本轮本机验证：与 Desktop workflow 相同的六个测试文件在开启诊断后 **76 passed / 9.21 秒**；未开启诊断的服务及生命周期子集 **35 passed / 8.82 秒**。Windows Ctrl+Break/TerminateProcess 分支待 Windows runner 实跑，macOS CI 卡点仍待下一轮栈证据。
