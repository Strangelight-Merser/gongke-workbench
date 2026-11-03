using System.Diagnostics;
using Microsoft.Win32;

namespace Gongke.Embed;

internal record Installation(string Id, string Kind, string Name, string Path);
internal record CadWindow(string Hwnd, int Pid, string Kind, string Title, string ClassName, uint Dpi, int Awareness, bool NativeMenu);
internal static class Discovery
{
    internal static string? Kind(string path) => System.IO.Path.GetFileName(path).ToLowerInvariant() switch
    { "freecad.exe" => "freecad", "sldworks.exe" => "solidworks", _ => null };

    internal static List<Installation> Installations(string? bundled)
    {
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void Add(string? path) { if (path != null && File.Exists(path) && Kind(path) != null) paths.Add(System.IO.Path.GetFullPath(path)); }
        Add(bundled);
        foreach (var hive in new[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
        {
            using var root = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64);
            foreach (var exe in new[] { "FreeCAD.exe", "SLDWORKS.exe" })
            {
                using var key = root.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\" + exe);
                Add((key?.GetValue("") as string)?.Trim('"'));
            }
            using var uninstall = root.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall");
            foreach (var name in uninstall?.GetSubKeyNames() ?? [])
            {
                using var key = uninstall!.OpenSubKey(name);
                var display = key?.GetValue("DisplayName") as string ?? "";
                var folder = key?.GetValue("InstallLocation") as string;
                if (string.IsNullOrWhiteSpace(folder)) continue;
                if (display.Contains("FreeCAD", StringComparison.OrdinalIgnoreCase)) Add(System.IO.Path.Combine(folder, "bin", "FreeCAD.exe"));
                if (display.Contains("SOLIDWORKS", StringComparison.OrdinalIgnoreCase))
                { Add(System.IO.Path.Combine(folder, "SLDWORKS.exe")); Add(System.IO.Path.Combine(folder, "SOLIDWORKS", "SLDWORKS.exe")); }
            }
        }
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        foreach (var folder in Directory.EnumerateDirectories(programFiles, "FreeCAD*")) Add(System.IO.Path.Combine(folder, "bin", "FreeCAD.exe"));
        Add(System.IO.Path.Combine(programFiles, "SOLIDWORKS Corp", "SOLIDWORKS", "SLDWORKS.exe"));
        return paths.Select(p => new Installation(p, Kind(p)!, $"{(Kind(p) == "freecad" ? "FreeCAD" : "SOLIDWORKS")} {FileVersionInfo.GetVersionInfo(p).ProductVersion}", p)).OrderBy(p => p.Kind).ToList();
    }

    internal static CadWindow? Describe(nint hwnd)
    {
        if (!Win32.IsWindow(hwnd)) return null;
        try
        {
            using var process = Process.GetProcessById(Win32.Pid(hwnd));
            var kind = Kind(process.MainModule!.FileName);
            if (kind == null) return null;
            return new(hwnd.ToInt64().ToString(), process.Id, kind, Win32.Title(hwnd), Win32.Class(hwnd), Win32.GetDpiForWindow(hwnd),
                Win32.GetAwarenessFromDpiAwarenessContext(Win32.GetWindowDpiAwarenessContext(hwnd)), Win32.GetMenu(hwnd) != 0);
        }
        catch (System.ComponentModel.Win32Exception) { return null; } // 高权限宿主不能由普通权限进程托管。
        catch (ArgumentException) { return null; } // 枚举期间进程已退出。
        catch (InvalidOperationException) { return null; }
    }
    internal static List<CadWindow> Windows() => Win32.Windows()
        .Where(w => Win32.IsWindowVisible(w) && Win32.GetWindow(w, 4) == 0 && !string.IsNullOrEmpty(Win32.Title(w)))
        .Select(Describe).OfType<CadWindow>().ToList();
}
