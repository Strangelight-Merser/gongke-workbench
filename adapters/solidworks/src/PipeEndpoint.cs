using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Gongke.SolidWorks
{
    internal sealed class PipeEndpoint : IDisposable
    {
        private readonly string token;
        private readonly string pipeName;
        private readonly string discoveryPath;
        private readonly HostDispatcher dispatcher;
        private readonly object gate = new object();
        private NamedPipeServerStream current;
        private volatile bool disposed;

        public PipeEndpoint(HostDispatcher dispatcher, string sessionId, string revision, string root)
        {
            this.dispatcher = dispatcher;
            var bytes = new byte[32];
            using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
            token = Convert.ToBase64String(bytes);
            var pid = Process.GetCurrentProcess().Id;
            pipeName = "Gongke_SolidWorks_" + pid + "_" + sessionId;
            var hosts = Path.Combine(root, "hosts");
            Directory.CreateDirectory(hosts);
            var security = new DirectorySecurity();
            security.SetAccessRuleProtection(true, false);
            security.AddAccessRule(new FileSystemAccessRule(WindowsIdentity.GetCurrent().User,
                FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None, AccessControlType.Allow));
            new DirectoryInfo(hosts).SetAccessControl(security);
            discoveryPath = Path.Combine(hosts, "solidworks-" + pid + ".json");
            File.WriteAllText(discoveryPath, new JObject {
                ["host"] = "solidworks", ["protocol_version"] = 1, ["pid"] = pid,
                ["session_id"] = sessionId, ["pipe_name"] = pipeName, ["token"] = token,
                ["host_revision"] = revision, ["started_at"] = DateTime.UtcNow.ToString("o"),
                ["capabilities"] = new JArray(HostOperations.Methods), ["native_validation"] = "unverified"
            }.ToString(Formatting.Indented), new UTF8Encoding(false));
            Task.Run((Func<Task>)Serve);
        }

        private async Task Serve()
        {
            while (!disposed)
            {
                var security = new PipeSecurity();
                security.SetAccessRuleProtection(true, false);
                security.AddAccessRule(new PipeAccessRule(WindowsIdentity.GetCurrent().User, PipeAccessRights.FullControl, AccessControlType.Allow));
                using (var pipe = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 65536, 65536, security))
                {
                    lock (gate) { if (disposed) return; current = pipe; }
                    try
                    {
                        await pipe.WaitForConnectionAsync().ConfigureAwait(false);
                        using (var reader = new StreamReader(pipe, new UTF8Encoding(false, true), false, 4096, true))
                        using (var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true })
                        {
                            while (!disposed && pipe.IsConnected)
                            {
                                var line = await ReadLine(reader).ConfigureAwait(false);
                                if (line == null) break;
                                JObject request = null;
                                JObject response;
                                try
                                {
                                    request = JObject.Parse(line);
                                    if (!TokenMatches((string)request["token"])) throw new CommandError("unauthorized", "Invalid endpoint token.");
                                    Protocol.Required(request, "method");
                                    if (!(request["params"] is JObject)) throw new CommandError("invalid_request", "params must be an object.");
                                    response = await dispatcher.Submit(request).ConfigureAwait(false);
                                }
                                catch (Exception error) { response = Protocol.Error(request?["id"], error); }
                                await writer.WriteLineAsync(response.ToString(Formatting.None)).ConfigureAwait(false);
                            }
                        }
                    }
                    catch (IOException) { }
                    catch (ObjectDisposedException) { }
                    catch (Exception error) { Trace.TraceError("Gongke SOLIDWORKS pipe: " + error); }
                    finally { lock (gate) { current = null; } }
                }
            }
        }

        private bool TokenMatches(string candidate)
        {
            if (candidate == null || candidate.Length != token.Length) return false;
            var difference = 0;
            for (var i = 0; i < token.Length; i++) difference |= token[i] ^ candidate[i];
            return difference == 0;
        }

        private static async Task<string> ReadLine(StreamReader reader)
        {
            var line = new StringBuilder();
            var buffer = new char[1];
            while (await reader.ReadAsync(buffer, 0, 1).ConfigureAwait(false) != 0)
            {
                if (buffer[0] == '\n') return line.ToString().TrimEnd('\r');
                if (line.Length == Protocol.MaxRequestCharacters) throw new IOException("Request exceeds 1 MiB.");
                line.Append(buffer[0]);
            }
            return line.Length == 0 ? null : line.ToString();
        }

        public void Dispose()
        {
            disposed = true;
            lock (gate) { current?.Dispose(); }
            if (File.Exists(discoveryPath)) File.Delete(discoveryPath);
        }
    }
}
