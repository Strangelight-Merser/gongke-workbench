using System.Diagnostics;
using System.Text.Json;

namespace Gongke.Embed;

internal record SavedWindow(long Hwnd, int Pid, long Started, long Parent, long Owner, long Style, long ExStyle,
    int X, int Y, int Width, int Height, bool Maximized);
internal record Viewport(int X, int Y, int Width, int Height, bool Visible);
internal sealed class Session
{
    internal readonly SavedWindow Saved;
    internal readonly string Mode;
    internal nint Hwnd => (nint)Saved.Hwnd;
    readonly nint parent;
    readonly string recovery;
    readonly HashSet<nint> hiddenPopups = [];
    Win32.Rect lastParent;
    bool parentDisabled;
    Viewport? applied;
    bool? shown;
    string savedPopups = "";
    internal Session(nint parent, nint hwnd, string mode, string logDirectory)
    {
        if (mode is not ("embed" or "dock")) throw new ArgumentException("未知窗口模式");
        if (!Win32.IsWindowEnabled(hwnd)) throw new InvalidOperationException("请先完成 CAD 中的对话框");
        var original = Discovery.Describe(hwnd) ?? throw new InvalidOperationException("CAD 窗口已退出或无法访问");
        if (Win32.GetWindow(hwnd, 4) != 0 || (Win32.GetLong(hwnd, Win32.Style).ToInt64() & Win32.Child) != 0)
            throw new InvalidOperationException("只能选择 CAD 顶层主窗口");
        using var process = Process.GetProcessById(original.Pid);
        Win32.GetWindowRect(hwnd, out var rect);
        Saved = new(hwnd.ToInt64(), original.Pid, process.StartTime.ToUniversalTime().Ticks,
            Win32.GetParent(hwnd).ToInt64(), Win32.GetWindow(hwnd, 4).ToInt64(),
            Win32.GetLong(hwnd, Win32.Style).ToInt64(), Win32.GetLong(hwnd, Win32.ExStyle).ToInt64(),
            rect.Left, rect.Top, rect.Right - rect.Left, rect.Bottom - rect.Top, IsZoomed(hwnd));
        this.parent = parent;
        Mode = mode;
        recovery = Path.Combine(logDirectory, $"recovery-{Guid.NewGuid():N}.json");
        File.WriteAllText(recovery, JsonSerializer.Serialize(Saved, Program.Json));
        // 独立守护进程先就绪再重挂；仅恢复窗口，绝不终止或保存 CAD。
        var start = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true };
        foreach (var arg in new[] { "--guard", recovery, Environment.ProcessId.ToString(), Win32.Pid(parent).ToString() }) start.ArgumentList.Add(arg);
        using var guard = Process.Start(start) ?? throw new InvalidOperationException("窗口恢复守护进程未启动");
        var ready = recovery + ".ready";
        if (!SpinWait.SpinUntil(() => File.Exists(ready) || guard.HasExited, 5000) || !File.Exists(ready))
        { File.Delete(recovery); throw new InvalidOperationException("窗口恢复守护进程未就绪"); }
        File.Delete(ready);
        try
        {
            Win32.ShowWindowAsync(hwnd, 9); // 取消最大化，窗口尺寸由编辑区控制。
            if (mode == "embed")
            {
                Win32.Long(hwnd, Win32.Style, (Saved.Style | Win32.Child) & ~(Win32.Popup | Win32.Caption | Win32.ThickFrame));
                Win32.Long(hwnd, Win32.ExStyle, Saved.ExStyle & ~Win32.AppWindow);
                Win32.Parent(hwnd, parent);
            }
            else Win32.Long(hwnd, Win32.Owner, parent.ToInt64());
            Win32.GetWindowRect(parent, out lastParent);
        }
        catch { Restore(Saved); File.Delete(recovery); throw; }
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool IsZoomed(nint hwnd);
    internal bool Alive => Matches(Saved);
    internal static bool Matches(SavedWindow s)
    {
        if (!Win32.IsWindow((nint)s.Hwnd) || Win32.Pid((nint)s.Hwnd) != s.Pid) return false;
        try { using var p = Process.GetProcessById(s.Pid); return p.StartTime.ToUniversalTime().Ticks == s.Started; }
        catch (ArgumentException) { return false; }
    }
    internal List<nint> Popups() => Win32.Windows().Where(w =>
    {
        if (Win32.Pid(w) != Saved.Pid || w == Hwnd) return false;
        for (var owner = Win32.GetWindow(w, 4); owner != 0; owner = Win32.GetWindow(owner, 4))
            if (owner == Hwnd) return true;
        return false;
    }).ToList();

    internal void Layout(Viewport v)
    {
        if (!Alive) return;
        var visible = v.Visible && !Win32.IsIconic(parent) && Win32.IsWindowVisible(parent) && v.Width > 0 && v.Height > 0;
        // 使用父 HWND 的 DPI 上下文转换屏幕物理坐标，不用显示器倍率推算客户区边框。
        if (applied != v)
        {
        var context = Win32.SetThreadDpiAwarenessContext(Win32.GetWindowDpiAwarenessContext(parent));
        try
        {
            var point = new Win32.Point { X = v.X, Y = v.Y };
            if (Mode == "embed") Win32.Check(Win32.ScreenToClient(parent, ref point));
            Win32.Check(Win32.SetWindowPos(Hwnd, 0, point.X, point.Y, Math.Max(1, v.Width), Math.Max(1, v.Height),
                Win32.NoActivate | Win32.FrameChanged | Win32.Async | Win32.NoOwnerZOrder));
        }
        finally { Win32.SetThreadDpiAwarenessContext(context); }
        applied = v;
        }
        if (shown != visible) { Win32.ShowWindowAsync(Hwnd, visible ? 8 : 0); shown = visible; }
        Win32.GetWindowRect(parent, out var current);
        var dx = current.Left - lastParent.Left; var dy = current.Top - lastParent.Top;
        foreach (var popup in Popups())
        {
            if (Win32.Class(popup) == "#32768") continue; // 菜单由 CAD 自己定位。
            if (!visible && Win32.IsWindowVisible(popup)) { hiddenPopups.Add(popup); SavePopups(); Win32.ShowWindowAsync(popup, 0); }
            if (visible && hiddenPopups.Remove(popup)) Win32.ShowWindowAsync(popup, 8);
            if (!visible || !Win32.IsWindowVisible(popup)) continue;
            Win32.GetWindowRect(popup, out var r);
            var area = Screen.FromHandle(parent).WorkingArea;
            var x = Math.Clamp(r.Left + dx, area.Left, Math.Max(area.Left, area.Right - (r.Right - r.Left)));
            var y = Math.Clamp(r.Top + dy, area.Top, Math.Max(area.Top, area.Bottom - (r.Bottom - r.Top)));
            if (x != r.Left || y != r.Top)
                Win32.Check(Win32.SetWindowPos(popup, 0, x, y, r.Right - r.Left, r.Bottom - r.Top, Win32.NoActivate | Win32.Async | 4));
        }
        SavePopups();
        if (!Win32.IsIconic(parent)) lastParent = current;
        var modal = !Win32.IsWindowEnabled(Hwnd);
        if (modal != parentDisabled) { Win32.EnableWindow(parent, !modal); parentDisabled = modal; }
    }
    void SavePopups()
    {
        var json = JsonSerializer.Serialize(hiddenPopups.Select(w => w.ToInt64()).ToArray(), Program.Json);
        if (json == savedPopups) return;
        File.WriteAllText(recovery + ".popups.tmp", json);
        File.Move(recovery + ".popups.tmp", recovery + ".popups", true);
        savedPopups = json;
    }
    internal void Detach()
    {
        if (parentDisabled) Win32.EnableWindow(parent, true);
        Restore(Saved);
        foreach (var popup in hiddenPopups) if (Win32.IsWindow(popup)) Win32.ShowWindowAsync(popup, 8);
        hiddenPopups.Clear();
        File.Delete(recovery + ".popups");
        File.Delete(recovery);
    }
    internal static void Restore(SavedWindow s)
    {
        if (!Matches(s)) return;
        var w = (nint)s.Hwnd;
        Win32.Parent(w, (nint)s.Parent);
        Win32.Long(w, Win32.Style, s.Style);
        Win32.Long(w, Win32.ExStyle, s.ExStyle);
        Win32.Long(w, Win32.Owner, Win32.IsWindow((nint)s.Owner) ? s.Owner : 0);
        var area = Screen.FromHandle(w).WorkingArea;
        var x = Math.Clamp(s.X, area.Left, Math.Max(area.Left, area.Right - s.Width));
        var y = Math.Clamp(s.Y, area.Top, Math.Max(area.Top, area.Bottom - s.Height));
        Win32.Check(Win32.SetWindowPos(w, 0, x, y, s.Width, s.Height, Win32.FrameChanged | Win32.NoActivate | Win32.Async));
        Win32.ShowWindowAsync(w, s.Maximized ? 3 : 9);
    }
}
