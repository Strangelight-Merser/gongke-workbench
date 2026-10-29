using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using AcApplication = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using System.Runtime.InteropServices;

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
        commands = new HostCommands(server.Session);
        AcApplication.Idle += OnIdle;
        server.Start();
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
            // Native edits run in command context so normal AutoCAD command undo semantics apply.
            if (pending.Request.Method is "drawing.edit_text" or "drawing.move_dimension_text" or "document.select")
            {
                if (active is null) throw new BridgeException("no_document", "Open a drawing first.");
                await AcApplication.DocumentManager.ExecuteInCommandContextAsync(_ =>
                {
                    result = commands.Execute(pending.Request);
                    return Task.CompletedTask;
                }, null);
            }
            else result = commands.Execute(pending.Request);
            server.Complete(pending, result);
        }
        catch (System.Exception error) { server.Complete(pending, null, error); }
        finally { executing = false; }
    }
}
