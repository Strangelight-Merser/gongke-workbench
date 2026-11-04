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
        private readonly object gate = new object();
        private readonly TimeSpan timeout;
        private bool executing;
        // 由宿主线程上的消息窗口投递执行；SOLIDWORKS 2023 实机上 OnIdleNotify 不触发。
        public Action Notify;
        private volatile bool disposed;
        public HostDispatcher(Func<JObject, JObject> execute, TimeSpan? timeout = null)
        { this.execute = execute; this.timeout = timeout ?? TimeSpan.FromSeconds(45); }

        public async Task<JObject> Submit(JObject request)
        {
            var work = new Work { Request = request };
            lock (gate)
            {
                if (disposed) return Protocol.Error(request["id"], new CommandError("disconnected", "Add-in is unloading."));
                queue.Enqueue(work);
            }
            Notify?.Invoke();
            if (await Task.WhenAny(work.Completion.Task, Task.Delay(timeout)).ConfigureAwait(false) == work.Completion.Task)
                return await work.Completion.Task.ConfigureAwait(false);
            if (work.Completion.Task.IsCompleted) return await work.Completion.Task.ConfigureAwait(false);
            var cancelledBeforeStart = Interlocked.CompareExchange(ref work.State, 2, 0) == 0;
            return Protocol.Error(request["id"], new CommandError("host_timeout",
                cancelledBeforeStart ? "SOLIDWORKS was busy; command was cancelled before execution."
                    : "Host operation is still running. Query operation.get with the same operation_id; do not resubmit a new operation.",
                cancelledBeforeStart ? "not_applied" : "unknown"));
        }

        // 只在宿主 STA 线程由 StaPump 调用，不在管道线程执行。
        public void Drain()
        {
            if (Thread.CurrentThread.ManagedThreadId != hostThread || executing) return;
            Work work;
            lock (gate)
            {
                if (disposed || !queue.TryDequeue(out work) || Interlocked.CompareExchange(ref work.State, 1, 0) != 0) return;
                executing = true;
            }
            // STA 中的 COM 调用可以泵消息并再次进入 Drain；锁不能阻止同线程重入。
            try
            {
                try { work.Completion.TrySetResult(execute(work.Request)); }
                catch (Exception error) { work.Completion.TrySetResult(Protocol.Error(work.Request["id"], error, "unknown")); }
            }
            finally { executing = false; }
            // 重入期间被跳过的投递在此补发。
            if (!queue.IsEmpty) Notify?.Invoke();
        }

        public void Dispose()
        {
            lock (gate)
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
}
