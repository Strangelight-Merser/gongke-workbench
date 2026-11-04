using System.Diagnostics;
using System.Text.Json;
using Gongke.AutoCAD;

internal static class RecoveryChecks
{
    private static Request RequestFor(string id) => new("original-request", "drawing.import_dxf",
        JsonSerializer.SerializeToElement(new { operation_id = id, source_path = "source.dxf", target_path = "copy.dwg" }));

    // 子进程持有与插件相同的文件锁；父进程直接终止它，跳过 Dispose。
    internal static void Child(string folder, string state)
    {
        var store = new OperationStore(folder);
        using var lease = store.Begin(RequestFor(state), "original-session", out _)!;
        if (state != "queued") lease.Update("running", "unknown");
        if (state == "completed") lease.Update("completed", "committed", new { id = "original-request", result = new {
            path = "copy.dwg", native_fingerprint = "native-guid", disk_reopen_verified = true, original_preserved = true } });
        OperationStore.FlushTrace();
        Console.WriteLine("ready");
        Console.Out.Flush();
        Thread.Sleep(Timeout.Infinite);
    }

    internal static async Task Run(string temporary, Action<bool, string> check)
    {
        OperationStore.Trace("recovery.environment", new { os = System.Runtime.InteropServices.RuntimeInformation.OSDescription,
            runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription, temporary });
        var folder = Path.Combine(temporary, "restart");
        var store = new OperationStore(folder);
        foreach (var state in new[] { "queued", "running", "completed" })
        {
            var info = new ProcessStartInfo(Environment.ProcessPath!) { RedirectStandardOutput = true, UseShellExecute = false };
            if (Path.GetFileNameWithoutExtension(Environment.ProcessPath) == "dotnet")
                info.ArgumentList.Add(typeof(RecoveryChecks).Assembly.Location);
            foreach (var arg in new[] { "--crash-child", folder, state }) info.ArgumentList.Add(arg);
            using var child = Process.Start(info)!;
            try
            {
                check(await child.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10)) == "ready", "Child persists " + state);
                check(store.Get(state).Status == state, "Live cross-process status " + state);
                check(store.Begin(RequestFor(state), "second-session", out var live) is null && live!.Status == state,
                    "Second process cannot replay live operation " + state);
            }
            finally
            {
                OperationStore.Trace("child.kill", new { state, child.Id, child.HasExited });
                if (!child.HasExited) child.Kill();
                await child.WaitForExitAsync();
                OperationStore.Trace("child.wait-returned", new { state, child.Id, child.HasExited, child.ExitCode,
                    processHandleClosed = child.SafeHandle.IsClosed });
            }

            var restarted = new OperationStore(folder);
            // 普通文件读者不拥有操作；不能把共享访问冲突当作活跃写操作。
            using var reader = OperatingSystem.IsWindows()
                ? new FileStream(Path.ChangeExtension(store.RecordPath(state), ".lock"), FileMode.Open,
                    FileAccess.Read, FileShare.ReadWrite)
                : null;
            var recovered = restarted.Get(state);
            OperationStore.FlushTrace();
            var expected = state == "queued" ? "interrupted_before_start" : state == "running" ? "interrupted" : "completed";
            if (recovered.Status != expected)
            {
                // 只观察首次失败后的状态；不能以稍后恢复成功替代原断言。
                void Observe(string phase)
                {
                    try
                    {
                        var file = new FileInfo(Path.ChangeExtension(store.RecordPath(state), ".lock"));
                        OperationStore.Trace(phase, new { state, file.Exists, length = file.Exists ? file.Length : -1,
                            modified = file.Exists ? file.LastWriteTimeUtc : (DateTime?)null,
                            status = restarted.Get(state).Status });
                    }
                    catch (Exception e) { OperationStore.Trace(phase, new { state, type = e.GetType().Name, hresult = $"0x{e.HResult:X8}", e.Message }); }
                    finally { OperationStore.FlushTrace(); }
                }
                Observe("recovery.reader-open");
                reader?.Dispose();
                Observe("recovery.reader-closed");
                var processHandle = child.SafeHandle;
                child.Dispose();
                OperationStore.Trace("child.process-handle-disposed", new { state, processHandle.IsClosed });
                Observe("recovery.process-handle-closed");
                foreach (var delay in new[] { 10, 50, 200, 1000 })
                {
                    await Task.Delay(delay);
                    Observe("recovery.after-delay-" + delay);
                }
            }
            check(recovered.Status == expected,
                "Crash recovery state " + state + ": " + JsonSerializer.Serialize(recovered));
            check(recovered.Outcome == (state == "queued" ? "unchanged" : state == "running" ? "unknown" : "committed"),
                "Crash recovery outcome " + state);
            check(recovered.SessionId == "original-session" && recovered.Fingerprint == OperationStore.Fingerprint(RequestFor(state)),
                "Recovery preserves original session and fingerprint");
            check(restarted.Begin(RequestFor(state), "restarted-session", out _) is null, "Crash recovery never requeues " + state);
        }
        check(store.IsWorkingCopy("copy.dwg", "native-guid"), "Completed copy grants native permission after restart");
        check(!store.IsWorkingCopy("original.dwg", "native-guid") && !store.IsWorkingCopy("copy.dwg", "replaced-guid"),
            "Original and replaced drawings cannot acquire copy permission");
        check(store.Get("absent").Outcome == "unknown", "Missing record remains unknown");
        File.WriteAllText(store.RecordPath("completed"), "{truncated");
        check(store.Get("completed").Outcome == "unknown", "Corrupt record remains unknown");
        check(store.Begin(RequestFor("completed"), "restart", out _) is null, "Corruption cannot cause replay");
        File.Delete(store.RecordPath("running"));
        check(store.Get("running").Outcome == "unknown" && store.Begin(RequestFor("running"), "restart", out _) is null,
            "Missing snapshot with reserved ID cannot cause replay");

        // 真实文件系统故障：将目标 JSON 位置占为目录，原子发布必须失败。
        Directory.CreateDirectory(store.RecordPath("write-failed"));
        try { store.Begin(RequestFor("write-failed"), "session", out _); throw new Exception("Persistence unexpectedly succeeded"); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { check(true, "Initial persistence failure propagated"); }
        Directory.Delete(store.RecordPath("write-failed"));
        check(store.Begin(RequestFor("write-failed"), "session", out var failed) is null && failed!.Outcome == "unknown",
            "Failed initial publication retains reservation");
    }
}
