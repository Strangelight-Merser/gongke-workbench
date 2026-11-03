using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using AcApplication = Autodesk.AutoCAD.ApplicationServices.Core.Application;

[assembly: ExtensionApplication(typeof(Gongke.AutoCAD.Plugin))]

namespace Gongke.AutoCAD;

public sealed class Plugin : IExtensionApplication
{
    private BridgeServer? server;
    private HostCommands? commands;
    private bool executing;
    public void Initialize()
    {
        server = new BridgeServer();
        commands = new HostCommands(server.Session, server.Operations);
        server.Start();
        AcApplication.Idle += OnIdle;
    }
    public void Terminate()
    {
        AcApplication.Idle -= OnIdle;
        server?.Dispose();
        commands?.Dispose();
    }
    // Idle runs on AutoCAD's UI thread. No Autodesk object is ever touched by the pipe worker.
    private async void OnIdle(object? sender, EventArgs e)
    {
        if (executing || server is null || commands is null) return;
        var active = AcApplication.DocumentManager.MdiActiveDocument;
        if (active is not null && !active.Editor.IsQuiescent) return;
        if (!server.TryDequeue(out var pending) || pending is null) return;
        executing = true;
        try
        {
            object? result = null;
            System.Exception? commandError = null;
            // Native edits run in command context so normal AutoCAD command undo semantics apply.
            if (pending.Request.Method is "drawing.edit_text" or "drawing.move_dimension_text" or "document.select")
            {
                if (active is null) throw new BridgeException("no_document", "Open a drawing first.");
                await AcApplication.DocumentManager.ExecuteInCommandContextAsync(_ =>
                {
                    // 异常不能越过 AutoCAD 的原生命令回调边界。
                    try { result = commands.Execute(pending.Request); }
                    catch (System.Exception error) { commandError = error; }
                    return Task.CompletedTask;
                }, null);
            }
            else result = commands.Execute(pending.Request);
            server.Complete(pending, result, commandError);
        }
        catch (System.Exception error) { server.Complete(pending, null, error); }
        finally { executing = false; }
    }
}
