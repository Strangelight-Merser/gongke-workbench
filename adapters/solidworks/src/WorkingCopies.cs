using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json.Linq;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace Gongke.SolidWorks
{
    internal sealed partial class HostOperations
    {
        private sealed class SourceState
        {
            public string Path;
            public string Configuration;
            public bool Dirty;
            public int Revision;
            public string Hash;
        }

        private static string FileHash(string path)
        {
            using (var sha = SHA256.Create())
            using (var input = File.OpenRead(path)) return Convert.ToBase64String(sha.ComputeHash(input));
        }

        private static SourceState CaptureSource(ModelDoc2 model) => new SourceState {
            Path = model.GetPathName(), Configuration = Configuration(model), Dirty = model.GetSaveFlag(),
            Revision = model.GetUpdateStamp(), Hash = FileHash(model.GetPathName()) };

        private static bool SourceUnchanged(ModelDoc2 model, SourceState state) =>
            string.Equals(model.GetPathName(), state.Path, StringComparison.OrdinalIgnoreCase)
            && Configuration(model) == state.Configuration && model.GetSaveFlag() == state.Dirty
            && model.GetUpdateStamp() == state.Revision && FileHash(state.Path) == state.Hash;

        private static void RequireIndependentPart(ModelDoc2 part)
        {
            if (part.GetType() != (int)swDocumentTypes_e.swDocPART || part.IsOpenedViewOnly())
                throw new CommandError("unsupported_document", "A fully loaded part is required.");
            if (part.Extension.ListExternalFileReferencesCount() != 0)
                throw new CommandError("external_references", "Parts with external/in-context references require a separate copy workflow.");
        }

        private int ActivateExact(ModelDoc2 model)
        {
            int error = 0;
            nativeMutationStarted = true;
            var active = (ModelDoc2)app.ActivateDoc3(Path.GetFileName(model.GetPathName()), false,
                (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref error);
            if (active == null || !string.Equals(active.GetPathName(), model.GetPathName(), StringComparison.OrdinalIgnoreCase))
                throw new CommandError("activate_failed", "Cannot activate the exact source document; error=" + error, "unknown");
            return error;
        }

        private JObject CopyNative(ModelDoc2 model, string output)
        {
            if (File.Exists(output)) throw new CommandError("output_exists", "Copy output already exists.");
            // SaveAs3 的行为受选择集影响，保存前清空选择以复制整个模型。
            nativeMutationStarted = true;
            model.ClearSelection2(true);
            int errors = 0, warnings = 0;
            var ok = model.Extension.SaveAs3(output, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent | (int)swSaveAsOptions_e.swSaveAsOptions_Copy,
                null, null, ref errors, ref warnings);
            nativeEffectObserved |= File.Exists(output);
            if (!ok || errors != 0 || !File.Exists(output))
                throw new CommandError("copy_failed", "副本保存失败，保留产物供检查：" + output + "; errors=" + errors + ", warnings=" + warnings,
                    nativeEffectObserved ? "needs_review" : "unknown");
            return new JObject { ["path"] = output, ["errors"] = errors, ["warnings"] = warnings };
        }

        private static IEnumerable<View> ModelViews(ModelDoc2 drawing) => Items(((DrawingDoc)drawing).GetViews())
            .SelectMany(sheet => Items(sheet).Cast<View>().Skip(1));

        private static Dictionary<string, double> ParameterValues(JArray parameters)
        {
            var values = new Dictionary<string, double>(StringComparer.Ordinal);
            foreach (JObject item in parameters)
            {
                var name = (string)item["name"];
                var split = name.LastIndexOf('@');
                // SOLIDWORKS FullName ends with the document name, which changes in a copy.
                var key = split < 0 ? name : name.Substring(0, split);
                values.Add(key, (double)item["value"]);
            }
            return values;
        }

        private void RequireNewDocumentNames(params string[] paths)
        {
            var openNames = new HashSet<string>(Items(app.GetDocuments()).Cast<ModelDoc2>()
                .Select(document => Path.GetFileName(document.GetPathName())), StringComparer.OrdinalIgnoreCase);
            foreach (var path in paths)
                if (app.GetOpenDocumentByName(path) != null || openNames.Contains(Path.GetFileName(path)))
                    throw new CommandError("output_name_conflict", "目标文件名与已打开文档冲突，请使用新的文件名。");
        }

        private ModelDoc2 ReopenCopy(string path, swDocumentTypes_e type, string configuration, out int warnings)
        {
            // 不能让 OpenDoc6 返回已有内存文档，误充磁盘重开证据。
            if (app.GetOpenDocumentByName(path) != null)
                throw new CommandError("copy_unexpectedly_open", "副本已被打开，无法确认本次从磁盘加载：" + path, "needs_review");
            int errors = 0; warnings = 0;
            var copy = (ModelDoc2)app.OpenDoc6(path, (int)type,
                (int)swOpenDocOptions_e.swOpenDocOptions_Silent, configuration ?? "", ref errors, ref warnings);
            if (copy == null || errors != 0 || copy.GetType() != (int)type
                || !string.Equals(copy.GetPathName(), path, StringComparison.OrdinalIgnoreCase)
                || Configuration(copy) != configuration || copy.IsOpenedViewOnly() || copy.IsOpenedReadOnly())
                throw new CommandError("copy_reopen_failed", "副本重开未通过身份、配置或加载状态核对：" + path
                    + "; errors=" + errors + ", warnings=" + warnings, "needs_review");
            return copy;
        }

        private bool ValuesMatch(ModelDoc2 copy, Dictionary<string, double> expected)
        {
            var actual = ParameterValues(Parameters(copy));
            return actual.Count == expected.Count && expected.All(item =>
                actual.TryGetValue(item.Key, out var value) && Math.Abs(value - item.Value) <= 1e-10);
        }

        private JObject SavePartCopy(ModelDoc2 part, JObject p)
        {
            RequireIndependentPart(part);
            var output = Protocol.NewOutputPath(p, ".sldprt");
            RequireNewDocumentNames(output);
            var source = CaptureSource(part);
            var values = ParameterValues(Parameters(part));
            JObject receipt;
            try { receipt = CopyNative(part, output); }
            finally { if (source.Dirty && !part.GetSaveFlag()) part.SetSaveFlag(); }
            var copy = ReopenCopy(output, swDocumentTypes_e.swDocPART, source.Configuration, out var openWarnings);
            var activationWarnings = ActivateExact(copy);
            var valuesMatch = ValuesMatch(copy, values);
            var preserved = SourceUnchanged(part, source);
            var verified = valuesMatch && preserved && activationWarnings == 0 && openWarnings == 0 && (int)receipt["warnings"] == 0;
            var result = new JObject { ["status"] = verified ? "saved" : "needs_review",
                ["outcome"] = verified ? "applied" : "needs_review", ["path"] = output,
                ["file_exists"] = File.Exists(output), ["errors"] = receipt["errors"], ["warnings"] = receipt["warnings"],
                ["open_warnings"] = openWarnings, ["activation_warnings"] = activationWarnings, ["reopen_verified"] = true,
                ["parameter_values_verified"] = valuesMatch, ["source_state_preserved"] = preserved,
                ["source_part"] = source.Path, ["source_part_had_unsaved_edits"] = source.Dirty,
                ["document"] = Document(copy) };
            if (verified) workingCopies.Add(output);
            return result;
        }

        private JObject SaveDrawingCopy(ModelDoc2 drawing, JObject p)
        {
            var output = Protocol.NewOutputPath(p, ".slddrw");
            var partOutput = Protocol.NewOutputPath(new JObject { ["output_path"] = Protocol.Required(p, "output_part_path") }, ".sldprt");
            RequireNewDocumentNames(output, partOutput);
            var views = ModelViews(drawing).ToArray();
            if (views.Length == 0) throw new CommandError("unsupported_drawing", "Drawing has no model views.");
            var sources = views.Select(view => view.GetReferencedModelName()).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            var configurations = views.Select(view => view.ReferencedConfiguration).Distinct(StringComparer.Ordinal).ToArray();
            if (sources.Length != 1 || configurations.Length != 1 || !Path.IsPathRooted(sources[0])
                || !string.Equals(Path.GetExtension(sources[0]), ".sldprt", StringComparison.OrdinalIgnoreCase))
                throw new CommandError("unsupported_drawing", "Copy requires exactly one resolved part and one referenced configuration across all drawing views.");
            var sourcePath = Path.GetFullPath(sources[0]);
            var part = (ModelDoc2)app.GetOpenDocumentByName(sourcePath)
                ?? throw new CommandError("reference_not_loaded", "The referenced part must be fully loaded so unsaved edits are included.");
            RequireIndependentPart(part);
            if (p["expected_part_revision"]?.Type != JTokenType.Integer || (int)p["expected_part_revision"] != part.GetUpdateStamp())
                throw new CommandError("stale_reference", "Referenced part changed since review. Refresh document.context.");
            if (Configuration(part) != configurations[0])
                throw new CommandError("configuration_changed", "The referenced part must already have the drawing's configuration active.");
            if (views.Any(view => view.ReferencedDocument == null || !string.Equals(view.ReferencedDocument.GetPathName(), sourcePath, StringComparison.OrdinalIgnoreCase)))
                throw new CommandError("reference_unresolved", "A drawing view does not resolve to the expected loaded part.");
            var sourceDrawing = CaptureSource(drawing);
            var sourcePart = CaptureSource(part);
            var sourceValues = ParameterValues(Parameters(part));
            JObject partReceipt, drawingReceipt;
            try
            {
                ActivateExact(part);
                partReceipt = CopyNative(part, partOutput);
                ActivateExact(drawing);
                drawingReceipt = CopyNative(drawing, output);
            }
            finally
            {
                // Copying must never remove the user's pending-save indication for pre-existing edits.
                if (sourcePart.Dirty && !part.GetSaveFlag()) part.SetSaveFlag();
                if (sourceDrawing.Dirty && !drawing.GetSaveFlag()) drawing.SetSaveFlag();
                // Restore the original drawing focus even when a copy fails. Never close/save the originals.
                ActivateExact(drawing);
            }
            if (!SourceUnchanged(part, sourcePart) || !SourceUnchanged(drawing, sourceDrawing))
                throw new CommandError("source_state_changed", "Source path, dirty state, revision or disk bytes changed during copy. Outputs were preserved; inspect both originals before continuing.", "needs_review");
            if (app.GetOpenDocumentByName(output) != null)
                throw new CommandError("copy_unexpectedly_open", "New drawing is open; reference replacement requires it to be closed.", "needs_review");
            // This API operates on the new closed drawing, never the user's original drawing.
            if (!app.ReplaceReferencedDocument(output, sourcePath, partOutput))
                throw new CommandError("reference_replace_failed", "New drawing reference could not be replaced; partial copies were preserved.", "needs_review");
            var copiedPart = ReopenCopy(partOutput, swDocumentTypes_e.swDocPART, configurations[0], out var partOpenWarnings);
            var copiedDrawing = ReopenCopy(output, swDocumentTypes_e.swDocDRAWING, null, out var openWarnings);
            var activationWarnings = ActivateExact(copiedDrawing);
            var copiedViews = ModelViews(copiedDrawing).ToArray();
            var referencesMatch = copiedViews.Length == views.Length && copiedViews.All(view =>
                string.Equals(view.GetReferencedModelName(), partOutput, StringComparison.OrdinalIgnoreCase)
                && string.Equals(view.ReferencedDocument?.GetPathName(), partOutput, StringComparison.OrdinalIgnoreCase)
                && view.ReferencedConfiguration == configurations[0]);
            var valuesMatch = ValuesMatch(copiedPart, sourceValues);
            var sourcesUnchanged = SourceUnchanged(part, sourcePart) && SourceUnchanged(drawing, sourceDrawing);
            var verified = referencesMatch && valuesMatch && sourcesUnchanged
                && activationWarnings == 0 && openWarnings == 0 && partOpenWarnings == 0
                && (int)partReceipt["warnings"] == 0 && (int)drawingReceipt["warnings"] == 0;
            partReceipt["verified"] = verified;
            drawingReceipt["verified"] = verified;
            var result = new JObject { ["status"] = verified ? "saved" : "needs_review", ["path"] = output,
                ["outcome"] = verified ? "applied" : "needs_review",
                ["references_verified"] = referencesMatch, ["parameter_values_verified"] = valuesMatch,
                ["source_state_preserved"] = sourcesUnchanged, ["source_part"] = sourcePart.Path,
                ["source_drawing"] = sourceDrawing.Path, ["source_part_had_unsaved_edits"] = sourcePart.Dirty,
                ["source_drawing_had_unsaved_edits"] = sourceDrawing.Dirty, ["open_warnings"] = openWarnings,
                ["activation_warnings"] = activationWarnings,
                ["working_copies"] = new JArray(partReceipt, drawingReceipt), ["document"] = Document(copiedDrawing),
                ["drawing_inspection"] = Drawing(copiedDrawing), ["reopen_verified"] = true, ["part_open_warnings"] = partOpenWarnings,
                ["native_validation"] = "unverified" };
            if (verified) { workingCopies.Add(output); workingCopies.Add(partOutput); }
            return result;
        }
    }
}
