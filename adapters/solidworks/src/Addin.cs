using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swpublished;

namespace Gongke.SolidWorks
{
    [ComVisible(true)]
    [ClassInterface(ClassInterfaceType.None)]
    [Guid("507DA194-5B1B-4B32-B4A8-B3EA18B036FA")]
    [ProgId("Gongke.SolidWorks.Addin")]
    public sealed class Addin : ISwAddin
    {
        private SldWorks app;
        private HostDispatcher dispatcher;
        private PipeEndpoint endpoint;

        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            try
            {
                app = (SldWorks)ThisSW;
                if (!app.SetAddinCallbackInfo2(0, this, Cookie)) return false;
                var root = Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "Gongke");
                var sessionId = Guid.NewGuid().ToString("N");
                var operations = new HostOperations(app, sessionId, new OperationJournal(Path.Combine(root, "receipts", "solidworks", sessionId)));
                dispatcher = new HostDispatcher(operations.Execute);
                app.OnIdleNotify += dispatcher.OnIdle;
                endpoint = new PipeEndpoint(dispatcher, sessionId, app.RevisionNumber(), root);
                return true;
            }
            catch (Exception error)
            {
                Trace.TraceError("Gongke SOLIDWORKS load failed: " + error);
                try
                {
                    var directory = Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "Gongke", "diagnostics");
                    Directory.CreateDirectory(directory);
                    File.AppendAllText(Path.Combine(directory, "solidworks-load.log"), DateTime.UtcNow.ToString("o") + " " + error + System.Environment.NewLine);
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
                DisconnectFromSW();
                return false;
            }
        }

        public bool DisconnectFromSW()
        {
            endpoint?.Dispose();
            endpoint = null;
            if (app != null && dispatcher != null) app.OnIdleNotify -= dispatcher.OnIdle;
            dispatcher?.Dispose();
            dispatcher = null;
            // SOLIDWORKS owns its application RCW; do not FinalReleaseComObject it.
            app = null;
            return true;
        }
    }
}
