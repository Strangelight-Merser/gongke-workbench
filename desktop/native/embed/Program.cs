using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace Gongke.Embed;

internal static class Program
{
    internal static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
    static readonly object outputLock = new();
    [STAThread]
    static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        if (args.Length == 4 && args[0] == "--guard") { Guard(args); return; }
        if (args.Length != 4) throw new ArgumentException("需要 parent HWND、parent PID、日志目录和随包 FreeCAD 路径");
        Console.InputEncoding = new UTF8Encoding(false); Console.OutputEncoding = new UTF8Encoding(false);
        var parent = (nint)long.Parse(args[0]);
        if (Win32.Pid(parent) != int.Parse(args[1])) throw new ArgumentException("父窗口身份不匹配");
        Directory.CreateDirectory(args[2]);
        using var host = new Host(parent, args[2], args[3]);
        host.StartReader();
        Application.Run();
    }
    internal static void Write(object value) { lock (outputLock) Console.WriteLine(JsonSerializer.Serialize(value, Json)); }
    static void Guard(string[] args)
    {
        var path = args[1];
        using var helper = Process.GetProcessById(int.Parse(args[2]));
        using var parent = Process.GetProcessById(int.Parse(args[3]));
        File.WriteAllText(path + ".ready", "ready");
        while (File.Exists(path) && !helper.HasExited && !parent.HasExited) Thread.Sleep(100);
        if (!File.Exists(path)) return;
        try
        {
            var saved = JsonSerializer.Deserialize<SavedWindow>(File.ReadAllText(path), Json)!;
            Session.Restore(saved);
            if (File.Exists(path + ".popups"))
            {
                foreach (var hwnd in JsonSerializer.Deserialize<long[]>(File.ReadAllText(path + ".popups"), Json)!)
                    if (Win32.IsWindow((nint)hwnd) && Win32.Pid((nint)hwnd) == saved.Pid) Win32.ShowWindowAsync((nint)hwnd, 8);
                File.Delete(path + ".popups");
            }
            // 父窗口仍存活时解除窗口级模态禁用；CAD 自己仍保留原模态状态。
            foreach (var w in Win32.Windows().Where(w => Win32.Pid(w) == parent.Id)) Win32.EnableWindow(w, true);
            File.AppendAllText(Path.Combine(Path.GetDirectoryName(path)!, "recovery.jsonl"),
                JsonSerializer.Serialize(new { at = DateTime.UtcNow, saved.Pid, windowAlive = Session.Matches(saved), restored = Session.Matches(saved) && Win32.GetParent((nint)saved.Hwnd).ToInt64() == saved.Parent }, Json) + "\n");
            File.Delete(path);
        }
        catch (Exception e) { File.WriteAllText(path + ".error", e.ToString()); }
    }
}

internal sealed class Host : NativeWindow, IDisposable
{
    readonly nint parent;
    readonly int parentPid;
    readonly string logDirectory, bundled;
    readonly Control dispatch = new();
    readonly System.Windows.Forms.Timer timer = new() { Interval = 100 };
    readonly List<Process> launched = [];
    Session? session;
    Viewport viewport = new(0, 0, 1, 1, false);
    List<Installation> installations = [];
    bool hotkey, closing;
    nint lastCadFocus;
    string? error;
    internal Host(nint parent, string logDirectory, string bundled)
    {
        this.parent = parent; parentPid = Win32.Pid(parent); this.logDirectory = logDirectory; this.bundled = bundled;
        CreateHandle(new CreateParams { Caption = "Gongke embed controller", Parent = (nint)(-3) });
        _ = dispatch.Handle;
        timer.Tick += (_, _) => Tick(); timer.Start();
    }
    internal void StartReader() => Task.Run(() =>
    {
        string? line;
        while ((line = Console.ReadLine()) != null)
        {
            var request = line;
            dispatch.BeginInvoke(() => Receive(request));
        }
        dispatch.BeginInvoke(() => { Detach(); Application.ExitThread(); });
    });
    void Receive(string line)
    {
        long id = 0;
        try
        {
            using var doc = JsonDocument.Parse(line); var root = doc.RootElement;
            id = root.GetProperty("id").GetInt64();
            var method = root.GetProperty("method").GetString()!;
            var p = root.GetProperty("params");
            var result = Call(method, p);
            Program.Write(new { id, result });
            if (method != "layout" && method != "status") Log(method, result);
        }
        catch (Exception e) { error = e.Message; Program.Write(new { id, error = e.Message }); Log("error", new { message = e.ToString() }); }
    }
    object Call(string method, JsonElement p)
    {
        switch (method)
        {
            case "discover":
                installations = Discovery.Installations(bundled).Concat(installations.Where(i => File.Exists(i.Path)))
                    .DistinctBy(i => i.Path, StringComparer.OrdinalIgnoreCase).ToList();
                return new { installations, windows = Discovery.Windows() };
            case "addInstallation":
                var path = p.GetProperty("path").GetString()!;
                var kind = Discovery.Kind(path);
                if (kind == null || !File.Exists(path)) throw new ArgumentException("请选择 FreeCAD.exe 或 SLDWORKS.exe");
                var item = new Installation(Path.GetFullPath(path), kind, kind == "freecad" ? "FreeCAD" : "SOLIDWORKS", Path.GetFullPath(path));
                installations.RemoveAll(i => string.Equals(i.Path, item.Path, StringComparison.OrdinalIgnoreCase)); installations.Add(item);
                return new { installations, windows = Discovery.Windows() };
            case "launch":
                var install = installations.Single(i => i.Id == p.GetProperty("id").GetString());
                var existing = launched.FirstOrDefault(i => !i.HasExited && string.Equals(i.MainModule?.FileName, install.Path, StringComparison.OrdinalIgnoreCase));
                if (existing != null) return new { pid = existing.Id };
                var process = Process.Start(new ProcessStartInfo(install.Path) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(install.Path)! })!;
                launched.Add(process); return new { pid = process.Id };
            case "attach":
                if (session != null) throw new InvalidOperationException("请先释放或关闭当前 CAD");
                var hwnd = (nint)long.Parse(p.GetProperty("hwnd").GetString()!);
                var candidate = Discovery.Windows().SingleOrDefault(w => w.Hwnd == hwnd.ToInt64().ToString() && w.Pid == p.GetProperty("pid").GetInt32());
                if (candidate == null) throw new InvalidOperationException("选中的 CAD 窗口已变化，请刷新窗口列表");
                session = new Session(parent, hwnd, p.GetProperty("mode").GetString()!, logDirectory);
                closing = false; error = null; timer.Start(); session.Layout(viewport); return Status();
            case "layout":
                viewport = JsonSerializer.Deserialize<Viewport>(p, Program.Json)!;
                session?.Layout(viewport); return new { ok = true };
            case "focus":
                FocusCad(); return Status();
            case "detach": Detach(); return Status();
            case "closeCad":
                var target = session?.Hwnd ?? 0; Detach();
                if (target != 0) Win32.Check(Win32.PostMessage(target, 0x10, 0, 0));
                return Status();
            case "prepareClose":
                // 借用的 CAD 仅恢复独立窗口；本应用启动的 CAD 收到原生关闭消息。
                Detach(); closing = true;
                foreach (var w in Discovery.Windows().Where(w => launched.Any(p => !p.HasExited && p.Id == w.Pid)))
                    Win32.Check(Win32.PostMessage((nint)long.Parse(w.Hwnd), 0x10, 0, 0));
                return Status();
            case "cancelClose": closing = false; return Status();
            case "status": return Status();
            case "diagnose":
                var report = new { at = DateTime.UtcNow, os = Environment.OSVersion.ToString(), parent = parent.ToInt64().ToString(),
                    parentDpi = Win32.GetDpiForWindow(parent), parentAwareness = Win32.GetAwarenessFromDpiAwarenessContext(Win32.GetWindowDpiAwarenessContext(parent)),
                    state = Status(), viewport, actualBounds = session == null ? null : WindowBounds(session.Hwnd), actualParent = session == null ? null : Win32.GetParent(session.Hwnd).ToInt64().ToString(),
                    actualStyle = session == null ? 0 : Win32.GetLong(session.Hwnd, Win32.Style).ToInt64(),
                    sameDpiContext = session == null || Win32.AreDpiAwarenessContextsEqual(Win32.GetWindowDpiAwarenessContext(parent), Win32.GetWindowDpiAwarenessContext(session.Hwnd)),
                    windows = Discovery.Windows(), ownedPopups = session?.Popups().Select(w => new { hwnd = w.ToInt64().ToString(), title = Win32.Title(w), className = Win32.Class(w), visible = Win32.IsWindowVisible(w), enabled = Win32.IsWindowEnabled(w) }).ToArray(),
                    displays = Screen.AllScreens.Select(s => new { s.DeviceName, s.Bounds, s.WorkingArea }).ToArray() };
                var filename = Path.Combine(logDirectory, $"diagnostic-{DateTime.UtcNow:yyyyMMdd-HHmmss-fff}.json");
                File.WriteAllText(filename, JsonSerializer.Serialize(report, Program.Json)); return new { path = filename };
            case "shutdown": Detach(); Application.ExitThread(); return new { ok = true };
            default: throw new ArgumentException("未知窗口操作");
        }
    }
    static Viewport WindowBounds(nint hwnd)
    {
        Win32.GetWindowRect(hwnd, out var r);
        return new(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top, Win32.IsWindowVisible(hwnd));
    }
    object Status() => new { supported = true, attached = session is { Alive: true } ? Discovery.Describe(session.Hwnd) : null,
        mode = session?.Mode, closing, pendingPids = launched.Where(p => !p.HasExited).Select(p => p.Id).ToArray(), error,
        helperPid = Environment.ProcessId, shortcut = hotkey };
    void Detach() { session?.Detach(); session = null; lastCadFocus = 0; }
    void FocusCad()
    {
        if (session is not { Alive: true }) return;
        var target = Win32.IsWindow(lastCadFocus) && Win32.Pid(lastCadFocus) == session.Saved.Pid ? lastCadFocus : session.Hwnd;
        Win32.Focus(target);
    }
    void Tick()
    {
        try
        {
            if (!Win32.IsWindow(parent) || Win32.Pid(parent) != parentPid) { Detach(); Application.ExitThread(); return; }
            if (session != null && !session.Alive) { Detach(); error = "CAD 窗口已关闭；请检查 CAD 恢复文件后重新打开"; Program.Write(new { @event = "state", state = Status() }); }
            session?.Layout(viewport);
            var focused = Win32.FocusedWindow();
            if (session != null && Win32.Pid(focused) == session.Saved.Pid) lastCadFocus = focused;
            var foreground = Win32.GetForegroundWindow();
            var active = session != null && (Win32.Pid(foreground) == session.Saved.Pid || Win32.Pid(foreground) == Win32.Pid(parent));
            if (active && !hotkey) hotkey = Win32.RegisterHotKey(Handle, 1, 0x4003, 0x75); // Ctrl+Alt+F6，仅在本工作流前台注册。
            if (!active && hotkey) { Win32.UnregisterHotKey(Handle, 1); hotkey = false; }
        }
        catch (Exception e) { error = e.Message; Log("tick-error", new { error }); timer.Stop(); Program.Write(new { @event = "state", state = Status() }); }
    }
    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x312 && session != null && Win32.IsWindowEnabled(session.Hwnd))
        {
            var foregroundPid = Win32.Pid(Win32.GetForegroundWindow());
            if (foregroundPid != parentPid && foregroundPid != session.Saved.Pid) { base.WndProc(ref m); return; }
            if (Win32.Pid(Win32.FocusedWindow()) == session.Saved.Pid)
            { Win32.Focus(parent); Program.Write(new { @event = "returnFocus" }); }
            else FocusCad();
        }
        base.WndProc(ref m);
    }
    void Log(string action, object data) => File.AppendAllText(Path.Combine(logDirectory, "embed.jsonl"), JsonSerializer.Serialize(new { at = DateTime.UtcNow, action, data }, Program.Json) + "\n");
    public void Dispose() { timer.Dispose(); if (hotkey) Win32.UnregisterHotKey(Handle, 1); Detach(); DestroyHandle(); dispatch.Dispose(); foreach (var p in launched) p.Dispose(); }
}
