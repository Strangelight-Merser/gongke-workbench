# 验收脚本与桌面的退出契约

`scripts/owned_processes.py` 只收尾本次登记的直接 Popen 子进程；它不是 Windows Job Object，也不承诺在所有者被强制终止后清理整棵进程树。不要将脚本的信号测试当成 Electron/FreeCAD 正常关闭验收。

| 入口 | 能保证的行为 | 验证 |
|---|---|---|
| 脚本正常返回、异常、KeyboardInterrupt | Python 能执行退出处理时，终止并等待登记的子进程 | 三个跨平台测试分别检查退出码、子进程身份消失 |
| POSIX SIGINT / SIGTERM | 已注册处理器执行收尾，再退出 | 父测试在就绪后真实发送信号，不在脚本内自杀 |
| Windows 控制台 Ctrl+C / Ctrl+Break | Python 获得 SIGINT / SIGBREAK 且主线程能处理时执行收尾；阻塞在不可中断原生调用时不保证及时响应 | KeyboardInterrupt 覆盖异常退出；真实控制事件测试使用独立进程组 + CTRL_BREAK_EVENT。登记子进程另建进程组，确保它必须由所有者清理，不能被同次广播直接杀死 |
| 关闭脚本的 Windows 控制台窗口 | CTRL_CLOSE_EVENT 不等同于 Python SIGTERM；当前没有 Win32 控制台关闭处理器，不能承诺 Python atexit 执行或子进程清理 | 不以 SIGTERM 冒充此事件，也不宣称已覆盖 |
| 任务管理器强制结束进程 / Windows TerminateProcess / POSIX SIGKILL | 所有者没有执行清理的机会，子进程可能保留 | 在隔离的测试进程组中真实 kill 所有者，验证该场景留下存活子进程，再由测试回收；这是不能保证清理的反例，不承诺任何外部监督环境中子进程一定存活 |
| 点击 Electron 工作台关闭/退出 | 走现有退出协商：检查未保存文档，处理 Agent、服务、helper 与受管 FreeCAD；取消退出应继续工作 | `windows-installed.cjs` 从已安装应用正常退出并检查所有登记 PID；窗口按钮、原生保存对话框仍按真机清单验收 |

Windows 不能用 `os.kill(pid, signal.SIGINT/SIGTERM)` 模拟 POSIX 信号：除控制台事件常量外，`os.kill` 调用 TerminateProcess，传入值成为退出码。run 41771770952 中父进程退出码正是 2、15；孙进程仍持有原测试继承的 stdout 管道，`communicate()` 的读取线程因等待 EOF 超时。

新测试输出写文件，孙进程 stdio 指向 DEVNULL，所有者退出等待和子进程存活断言分开。强制退出分支在 finally 中清理自己创建的测试进程，失败也执行，不查杀其他 CAD 或 Python 实例。测试不放宽 15 秒退出时限。

依据：[Python 3.11 os.kill](https://docs.python.org/3.11/library/os.html#os.kill)、[Popen.send_signal](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.send_signal)、[Microsoft GenerateConsoleCtrlEvent](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)、[控制台 HandlerRoutine](https://learn.microsoft.com/en-us/windows/console/handlerroutine)。Ctrl+C 不能限制到指定进程组，因此自动化使用可定向的 Ctrl+Break，避免中断同一控制台内的 CI runner。


run `41773061261` 的 force 用例暴露两处测试问题：

- macOS 捕获的 PID、启动时间相同，command 从 `.../bin/python` 变成 `.../Resources/Python.app/Contents/MacOS/Python`。原来 Popen 一返回就取身份，早于 Python 启动器 exec。现在由子进程运行 Python 代码后原子发布自身身份，所有者等就绪再进入退出场景。生产身份匹配规则不变。
- Windows 在 finally 的 `os.kill` 之后轮询 process_identity；存活检查通过后，映像查询返回 WinError 5。收尾现在持有带 TERMINATE/SYNCHRONIZE 权限的句柄，TerminateProcess 后等待同一个内核对象，确认完成后关闭句柄，不在销毁过程中重复查询映像。[微软文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess) 明确指出 TerminateProcess 异步返回，应使用 WaitForSingleObject 确认结束。没有将访问拒绝视为身份消失或吞掉异常。
