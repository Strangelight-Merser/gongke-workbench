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

        private void ActivateExact(ModelDoc2 model)
        {
            int error = 0;
            var active = (ModelDoc2)app.ActivateDoc3(model.GetTitle(), false,
                (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref error);
            if (active == null || !string.Equals(active.GetPathName(), model.GetPathName(), StringComparison.OrdinalIgnoreCase))
                throw new CommandError("activate_failed", "Cannot activate the exact source document; error=" + error, "unknown");
        }

        private JObject CopyNative(ModelDoc2 model, string output)
        {
            if (File.Exists(output)) throw new CommandError("output_exists", "Copy output already exists.");
            int errors = 0, warnings = 0;
            nativeMutationStarted = true;
            var ok = model.Extension.SaveAs3(output, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent | (int)swSaveAsOptions_e.swSaveAsOptions_Copy,
                null, null, ref errors, ref warnings);
            if (!ok || errors != 0 || !File.Exists(output))
                throw new CommandError("copy_failed", "Native copy failed. Partial outputs are preserved for inspection; errors=" + errors + ", warnings=" + warnings, "unknown");
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

        private JObject SaveDrawingCopy(ModelDoc2 drawing, JObject p)
        {
            var output = Protocol.NewOutputPath(p, ".slddrw");
            var partOutput = Protocol.NewOutputPath(new JObject { ["output_path"] = Protocol.Required(p, "output_part_path") }, ".sldprt");
            if (app.GetOpenDocumentByName(output) != null || app.GetOpenDocumentByName(partOutput) != null)
                throw new CommandError("output_open", "A target document is already open.");
            var openNames = new HashSet<string>(Items(app.GetDocuments()).Cast<ModelDoc2>()
                .Select(document => Path.GetFileName(document.GetPathName())), StringComparer.OrdinalIgnoreCase);
            if (openNames.Contains(Path.GetFileName(output)) || openNames.Contains(Path.GetFileName(partOutput)))
                throw new CommandError("output_name_conflict", "Use new part and drawing filenames, not names already open in SOLIDWORKS.");
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
                throw new CommandError("source_state_changed", "Source path, dirty state, revision or disk bytes changed during copy. Outputs were preserved; inspect both originals before continuing.", "unknown");
            if (app.GetOpenDocumentByName(output) != null)
                throw new CommandError("copy_unexpectedly_open", "New drawing is open; reference replacement requires it to be closed.", "unknown");
            // This API operates on the new closed drawing, never the user's original drawing.
            if (!app.ReplaceReferencedDocument(output, sourcePath, partOutput))
                throw new CommandError("reference_replace_failed", "New drawing reference could not be replaced; partial copies were preserved.", "unknown");
            int openErrors = 0, openWarnings = 0;
            var copiedDrawing = (ModelDoc2)app.OpenDoc6(output, (int)swDocumentTypes_e.swDocDRAWING,
                (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref openErrors, ref openWarnings);
            if (copiedDrawing == null || openErrors != 0)
                throw new CommandError("copy_reopen_failed", "Copied drawing could not be reopened; errors=" + openErrors + ", warnings=" + openWarnings, "unknown");
            ActivateExact(copiedDrawing);
            var copiedViews = ModelViews(copiedDrawing).ToArray();
            var referencesMatch = copiedViews.Length == views.Length && copiedViews.All(view =>
                string.Equals(view.GetReferencedModelName(), partOutput, StringComparison.OrdinalIgnoreCase)
                && string.Equals(view.ReferencedDocument?.GetPathName(), partOutput, StringComparison.OrdinalIgnoreCase)
                && view.ReferencedConfiguration == configurations[0]);
            var copiedPart = (ModelDoc2)app.GetOpenDocumentByName(partOutput);
            var valuesMatch = false;
            if (copiedPart != null && Configuration(copiedPart) == configurations[0])
            {
                var values = ParameterValues(Parameters(copiedPart));
                valuesMatch = values.Count == sourceValues.Count && sourceValues.All(item =>
                    values.TryGetValue(item.Key, out var actual) && Math.Abs(actual - item.Value) <= 1e-10);
            }
            var sourcesUnchanged = SourceUnchanged(part, sourcePart) && SourceUnchanged(drawing, sourceDrawing);
            var verified = referencesMatch && valuesMatch && sourcesUnchanged;
            partReceipt["verified"] = verified;
            drawingReceipt["verified"] = verified;
            return new JObject { ["status"] = verified ? "saved" : "needs_review", ["path"] = output,
                ["references_verified"] = referencesMatch, ["parameter_values_verified"] = valuesMatch,
                ["source_state_preserved"] = sourcesUnchanged, ["source_part"] = sourcePart.Path,
                ["source_drawing"] = sourceDrawing.Path, ["source_part_had_unsaved_edits"] = sourcePart.Dirty,
                ["source_drawing_had_unsaved_edits"] = sourceDrawing.Dirty, ["open_warnings"] = openWarnings,
                ["working_copies"] = new JArray(partReceipt, drawingReceipt), ["document"] = Document(copiedDrawing),
                ["drawing_inspection"] = Drawing(copiedDrawing), ["reopen_verified"] = verified,
                ["native_validation"] = "unverified" };
        }
    }
}
