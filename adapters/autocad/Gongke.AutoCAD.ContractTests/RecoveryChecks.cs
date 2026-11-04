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
        Console.WriteLine(JsonSerializer.Serialize(new { pid = Environment.ProcessId, state }));
        Console.Out.Flush();
        Thread.Sleep(Timeout.Infinite);
    }

    internal static async Task Run(string temporary, Action<bool, string> check)
    {
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
                var ready = JsonSerializer.Deserialize<JsonElement>((await child.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10)))!);
                check(ready.GetProperty("pid").GetInt32() == child.Id && ready.GetProperty("state").GetString() == state,
                    "Killed process is the actual lock owner " + state);
                check(store.Get(state).Status == state, "Live cross-process status " + state);
                check(store.Begin(RequestFor(state), "second-session", out var live) is null && live!.Status == state,
                    "Second process cannot replay live operation " + state);
            }
            finally { if (!child.HasExited) child.Kill(); await child.WaitForExitAsync(); }

            var restarted = new OperationStore(folder);
            // 普通文件读者不拥有操作；不能把共享访问冲突当作活跃写操作。
            using var reader = OperatingSystem.IsWindows()
                ? new FileStream(Path.ChangeExtension(store.RecordPath(state), ".lock"), FileMode.Open,
                    FileAccess.Read, FileShare.ReadWrite)
                : null;
            var recovered = restarted.Get(state);
            var expected = state == "queued" ? "interrupted_before_start" : state == "running" ? "interrupted" : "completed";
            // Windows 的进程退出通知不保证文件系统已释放字节锁；等待可观察的恢复条件，
            // 不把 WaitForExit 当成解锁屏障，也不按 PID 强行恢复或重放操作。
            var recovery = Stopwatch.StartNew();
            while (recovered.Status == state && recovered.Status != expected && recovery.Elapsed < TimeSpan.FromSeconds(10))
            {
                await Task.Delay(10);
                recovered = restarted.Get(state);
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
