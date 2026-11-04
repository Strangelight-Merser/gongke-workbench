# AutoCAD 强制退出后的回执诊断

基线 run `41774064329`（`4ee81ca`）：Windows 的 running 回执在 child.Kill + WaitForExitAsync 后仍返回 running/unknown。日志没有异常码和实际分支，不能据此确认 Defender、父进程 Process 句柄或 OS 锁释放延迟。字节范围锁改动没有解决此失败。

本轮不改变锁策略、回执语义或成功条件。`CONTRACT_DIAGNOSTICS` 只在契约测试项目定义；插件不输出诊断。关键路径仅将事件放入内存队列，首次恢复查询完成后才输出，减少日志 I/O 对竞争窗口的影响。stderr 每行 JSON 含 UTC、单调时钟 tick、PID、阶段及状态，不含令牌和请求参数，GitHub 原测试步骤直接保存输出：

- `lock.open-failed`：打开文件失败，记录异常类型、HResult、低 16 位原生码；与加锁失败区分。
- `lock.opened` / `lock.range-failed` / `lock.acquired`：文件句柄及字节范围锁结果。
- `get.missing` / `get.lock-conflict` / `get.lock-acquired`：Get 实际分支和读取的状态。
- `child.kill` / `child.wait-returned`：子进程 PID、退出状态/退出码、父进程所持 Process 句柄是否关闭。
- 首次恢复错误才额外观察：普通读者仍打开、读者关闭、Process.Dispose 后，以及再等待 10/50/200/1000 ms 后的 Get；同时记录锁文件存在性、长度、修改时间。**最后仍断言首次结果**，稍后恢复不能把 CI 变绿。

[微软 LockFileEx 文档](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex) 明确说明终止后系统释放字节锁所需时间取决于资源，未释放前仍可能拒绝访问。[TerminateProcess 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess) 说明终止是异步的，须等待完成；外部持有的 Process 句柄维持进程内核对象，并不等于拥有子进程的文件句柄。因此不能仅以 WaitForExitAsync 返回或 Process.Dispose 推定字节锁已释放。

读取结果时：33 表示字节范围锁冲突；32 表示共享模式冲突，不能当成活跃操作。普通共享读者不申请字节锁；扫描器若采用不兼容共享模式，可能导致文件打开冲突，但异常码无法证明进程就是 Defender。只有观察到相应错误后才考虑进一步定位持有者，不禁用 Defender、不增加产品重试或按 PID 强行恢复。顺序观察中同时经过了时间，某一步后成功不能单独证明 Dispose 是原因。

诊断定位后删除该编译符号、Trace 调用、额外观察及本说明；保留最终根因和回归测试。
