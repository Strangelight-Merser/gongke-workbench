using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Gongke.SolidWorks
{
    internal sealed class CommandError : Exception
    {
        public string Code { get; }
        public string Outcome { get; }
        public CommandError(string code, string message, string outcome = "not_applied") : base(message)
        { Code = code; Outcome = outcome; }
    }

    internal static class Protocol
    {
        public const int MaxRequestCharacters = 1024 * 1024;
        public static readonly HashSet<string> Writes = new HashSet<string>(StringComparer.Ordinal)
        { "parameter.change", "drawing.update", "document.save_copy", "document.save", "drawing.export" };

        public static string Required(JObject obj, string name)
        {
            var value = obj[name];
            if (value?.Type != JTokenType.String || string.IsNullOrWhiteSpace((string)value))
                throw new CommandError("invalid_request", "Missing string: " + name);
            return (string)value;
        }

        public static double Number(JObject obj, string name)
        {
            var value = obj[name];
            if (value == null || (value.Type != JTokenType.Float && value.Type != JTokenType.Integer))
                throw new CommandError("invalid_request", "Missing numeric value: " + name);
            var result = (double)value;
            if (double.IsNaN(result) || double.IsInfinity(result))
                throw new CommandError("invalid_request", name + " must be finite.");
            return result;
        }

        public static string OperationId(JObject parameters)
        {
            var value = Required(parameters, "operation_id");
            if (!Guid.TryParse(value, out var parsed))
                throw new CommandError("invalid_request", "operation_id must be a UUID.");
            return parsed.ToString("D");
        }

        public static JObject Error(JToken id, Exception error, string outcome = "not_applied")
        {
            var known = error as CommandError;
            return new JObject { ["id"] = id?.DeepClone(), ["error"] = new JObject {
                ["code"] = known?.Code ?? "host_error", ["message"] = error.Message,
                ["outcome"] = known?.Outcome ?? outcome } };
        }

        public static string Fingerprint(string method, JObject parameters)
        {
            JToken Canonical(JToken token) => token is JObject obj
                ? new JObject(obj.Properties().OrderBy(p => p.Name, StringComparer.Ordinal)
                    .Select(p => new JProperty(p.Name, Canonical(p.Value))))
                : token is JArray array ? new JArray(array.Select(Canonical)) : token.DeepClone();
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(method + "\n" + Canonical(parameters).ToString(Formatting.None)))).Replace("-", "").ToLowerInvariant();
        }

        public static string NewOutputPath(JObject parameters, string extension)
        {
            var value = Required(parameters, "output_path");
            if (!Path.IsPathRooted(value)) throw new CommandError("invalid_path", "Use an absolute output path.");
            value = Path.GetFullPath(value);
            if (!string.Equals(Path.GetExtension(value), extension, StringComparison.OrdinalIgnoreCase))
                throw new CommandError("invalid_path", "Expected output extension " + extension);
            if (!Directory.Exists(Path.GetDirectoryName(value))) throw new CommandError("invalid_path", "Output directory does not exist.");
            if (File.Exists(value) || Directory.Exists(value)) throw new CommandError("output_exists", "Output already exists; choose a new path.");
            return value;
        }
    }

    // A started receipt survives a host crash. It must never become an automatic retry.
    internal sealed class OperationJournal
    {
        private readonly string directory;
        public OperationJournal(string directory) { this.directory = directory; Directory.CreateDirectory(directory); }
        private string PathFor(string id) => Path.Combine(directory, Guid.Parse(id).ToString("D") + ".json");
        public JObject Get(string id) => File.Exists(PathFor(id)) ? JObject.Parse(File.ReadAllText(PathFor(id))) : null;
        public void Put(string id, JObject receipt)
        {
            var target = PathFor(id);
            var temporary = target + ".tmp";
            using (var file = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
            using (var writer = new StreamWriter(file, new UTF8Encoding(false)))
            {
                writer.Write(receipt.ToString(Formatting.None));
                writer.Flush();
                file.Flush(true);
            }
            if (File.Exists(target)) File.Replace(temporary, target, null);
            else File.Move(temporary, target);
        }
    }
}
