using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace Gongke.SolidWorks
{
    internal sealed class HostDispatcher : IDisposable
    {
        private sealed class Work
        {
            public JObject Request;
            public int State; // queued=0, executing=1, cancelled=2
            public TaskCompletionSource<JObject> Completion = new TaskCompletionSource<JObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        }
        private readonly ConcurrentQueue<Work> queue = new ConcurrentQueue<Work>();
        private readonly Func<JObject, JObject> execute;
        private readonly int hostThread = Thread.CurrentThread.ManagedThreadId;
        private volatile bool disposed;
        public HostDispatcher(Func<JObject, JObject> execute) { this.execute = execute; }

        public async Task<JObject> Submit(JObject request)
        {
            if (disposed) return Protocol.Error(request["id"], new CommandError("disconnected", "Add-in is unloading."));
            var work = new Work { Request = request };
            queue.Enqueue(work);
            if (await Task.WhenAny(work.Completion.Task, Task.Delay(TimeSpan.FromSeconds(45))).ConfigureAwait(false) == work.Completion.Task)
                return await work.Completion.Task.ConfigureAwait(false);
            var cancelledBeforeStart = Interlocked.CompareExchange(ref work.State, 2, 0) == 0;
            return Protocol.Error(request["id"], new CommandError("host_timeout",
                cancelledBeforeStart ? "SOLIDWORKS was busy; command was cancelled before execution."
                    : "Host operation is still running. Query operation.get with the same operation_id; do not resubmit a new operation.",
                cancelledBeforeStart ? "not_applied" : "unknown"));
        }

        // Called only from SOLIDWORKS OnIdleNotify, never from an IPC worker.
        public int OnIdle()
        {
            if (disposed || Thread.CurrentThread.ManagedThreadId != hostThread) return 0;
            if (queue.TryDequeue(out var work) && Interlocked.CompareExchange(ref work.State, 1, 0) == 0)
            {
                try { work.Completion.TrySetResult(execute(work.Request)); }
                catch (Exception error) { work.Completion.TrySetResult(Protocol.Error(work.Request["id"], error, "unknown")); }
            }
            return 0;
        }

        public void Dispose()
        {
            disposed = true;
            while (queue.TryDequeue(out var work))
            {
                Interlocked.CompareExchange(ref work.State, 2, 0);
                work.Completion.TrySetResult(Protocol.Error(work.Request["id"], new CommandError("disconnected", "Add-in unloaded before command execution.")));
            }
        }
    }
}
