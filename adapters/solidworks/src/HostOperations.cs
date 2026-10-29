using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace Gongke.SolidWorks
{
    internal sealed partial class HostOperations
    {
        public static readonly string[] Methods = {
            "host.info", "document.context", "document.open", "document.activate", "parameters.list", "parameter.change",
            "selection.get", "selection.set", "preview.mesh", "drawing.inspect", "drawing.update",
            "document.save_copy", "document.save", "drawing.export", "operation.get"
        };
        private readonly SldWorks app;
        private readonly string session;
        private readonly OperationJournal journal;
        private bool nativeMutationStarted;
        public HostOperations(SldWorks app, string session, OperationJournal journal)
        { this.app = app; this.session = session; this.journal = journal; }

        public JObject Execute(JObject request)
        {
            nativeMutationStarted = false;
            var id = request["id"];
            string operationId = null;
            string fingerprint = null;
            var started = false;
            try
            {
                var method = Protocol.Required(request, "method");
                var p = (JObject)request["params"];
                if (Protocol.Writes.Contains(method))
                {
                    if (Protocol.Required(p, "session_id") != session)
                        throw new CommandError("stale_session", "This request belongs to another SOLIDWORKS session.");
                    operationId = Protocol.OperationId(p);
                    fingerprint = Protocol.Fingerprint(method, p);
                    var previous = journal.Get(operationId);
                    if (previous != null)
                    {
                        if ((string)previous["fingerprint"] != fingerprint)
                            throw new CommandError("operation_conflict", "operation_id was already used for different parameters.");
                        if (previous["response"] is JObject saved)
                        {
                            var result = (JObject)saved.DeepClone(); result["id"] = id?.DeepClone(); return result;
                        }
                        throw new CommandError("operation_incomplete", "A previous attempt started without a final receipt. Inspect the document and receipt; automatic retry is disabled.", "unknown");
                    }
                    // Persist before entering any mutation. A crash cannot become an unrecorded retry.
                    journal.Put(operationId, new JObject { ["operation_id"] = operationId, ["session_id"] = session,
                        ["fingerprint"] = fingerprint, ["method"] = method, ["state"] = "started", ["started_at"] = DateTime.UtcNow.ToString("o") });
                    started = true;
                }
                var payload = Dispatch(method, p);
                var response = new JObject { ["id"] = id?.DeepClone(), ["result"] = payload };
                if (started) Finish(operationId, fingerprint, response);
                return response;
            }
            catch (Exception error)
            {
                if (nativeMutationStarted && error is CommandError known && known.Outcome == "not_applied")
                    error = new CommandError(known.Code, known.Message, "unknown");
                var response = Protocol.Error(id, error, started ? "unknown" : "not_applied");
                if (started)
                {
                    try { Finish(operationId, fingerprint, response); }
                    catch { return Protocol.Error(id, new CommandError("receipt_write_failed", "Native operation may have run but its final receipt could not be saved. Inspect current state; do not retry with a new operation_id.", "unknown")); }
                }
                return response;
            }
        }

        private void Finish(string id, string fingerprint, JObject response) => journal.Put(id,
            new JObject { ["operation_id"] = id, ["session_id"] = session, ["fingerprint"] = fingerprint,
                ["state"] = "finished", ["finished_at"] = DateTime.UtcNow.ToString("o"), ["response"] = response });

        private JToken Dispatch(string method, JObject p)
        {
            switch (method)
            {
                case "host.info": return new JObject { ["host"] = "solidworks", ["revision"] = app.RevisionNumber(),
                    ["session_id"] = session, ["protocol_version"] = 1, ["capabilities"] = new JArray(Methods),
                    ["native_validation"] = "unverified", ["length_unit"] = "m", ["angle_unit"] = "rad" };
                case "document.context": return Context();
                case "document.open": return Open(p);
                case "document.activate": return Activate(p);
                case "parameters.list": return Parameters(Bound(p));
                case "parameter.change": return Change(p);
                case "selection.get": return Selection(Bound(p));
                case "selection.set": return Select(p);
                case "preview.mesh": return Mesh(Bound(p));
                case "drawing.inspect": return Drawing(Bound(p));
                case "drawing.update": return UpdateDrawing(p);
                case "document.save_copy": return SaveCopy(p);
                case "document.save": return Save(p);
                case "drawing.export": return ExportDrawing(p);
                case "operation.get":
                    return journal.Get(Protocol.OperationId(p)) ?? new JObject { ["state"] = "not_found", ["session_id"] = session };
                default: throw new CommandError("unknown_method", "Unknown method: " + method);
            }
        }

        private static IEnumerable<object> Items(object value) => value is Array array ? array.Cast<object>() : Enumerable.Empty<object>();
        private static string Configuration(ModelDoc2 model) => model.GetType() == (int)swDocumentTypes_e.swDocDRAWING
            ? null : model.ConfigurationManager?.ActiveConfiguration?.Name;
        private static JObject Document(ModelDoc2 model) => new JObject {
            ["path"] = model.GetPathName(), ["title"] = model.GetTitle(), ["document_type"] = model.GetType(),
            ["configuration"] = Configuration(model), ["dirty"] = model.GetSaveFlag(),
            ["revision"] = model.GetUpdateStamp(), ["read_only_state"] = model.IsOpenedReadOnly(), ["view_only"] = model.IsOpenedViewOnly()
        };
        private JObject Context()
        {
            var documents = new JArray(Items(app.GetDocuments()).Cast<ModelDoc2>().Select(Document));
            var active = app.IActiveDoc2;
            return new JObject { ["session_id"] = session, ["active_document"] = active == null ? null : Document(active), ["documents"] = documents };
        }

        private ModelDoc2 Bound(JObject p, bool write = false)
        {
            var model = app.IActiveDoc2 ?? throw new CommandError("no_document", "Open a document in SOLIDWORKS.");
            if (model.IsOpenedViewOnly()) throw new CommandError("view_only", "Wait for the document to load fully; view-only documents are not supported.");
            var path = Protocol.Required(p, "document_path");
            if (string.IsNullOrWhiteSpace(model.GetPathName()) || !string.Equals(Path.GetFullPath(path), Path.GetFullPath(model.GetPathName()), StringComparison.OrdinalIgnoreCase))
                throw new CommandError("document_changed", "The requested document must be the active saved document.");
            if (model.GetType() != (int)swDocumentTypes_e.swDocDRAWING && Protocol.Required(p, "configuration") != Configuration(model))
                throw new CommandError("configuration_changed", "Activate the requested configuration before this operation.");
            if (write)
            {
                RequireRevision(model, p);
                if (model.IsOpenedReadOnly()) throw new CommandError("read_only", "Document is read-only.");
            }
            return model;
        }

        private static void RequireRevision(ModelDoc2 model, JObject parameters)
        {
            if (parameters["expected_revision"]?.Type != JTokenType.Integer || (int)parameters["expected_revision"] != model.GetUpdateStamp())
                throw new CommandError("stale_document", "Document changed since it was read. Refresh context and review the change.");
        }

        private JObject Open(JObject p)
        {
            var path = Path.GetFullPath(Protocol.Required(p, "document_path"));
            if (!File.Exists(path)) throw new CommandError("file_missing", "Document does not exist.");
            var extension = Path.GetExtension(path).ToLowerInvariant();
            var type = extension == ".sldprt" ? swDocumentTypes_e.swDocPART
                : extension == ".slddrw" ? swDocumentTypes_e.swDocDRAWING
                : throw new CommandError("unsupported_document", "Open supports native part and drawing files.");
            int errors = 0, warnings = 0;
            var model = (ModelDoc2)app.OpenDoc6(path, (int)type, (int)swOpenDocOptions_e.swOpenDocOptions_Silent,
                (string)p["configuration"] ?? "", ref errors, ref warnings);
            if (model == null) throw new CommandError("open_failed", "SOLIDWORKS open error=" + errors + ", warning=" + warnings);
            var result = Activate(p);
            result["open_errors"] = errors; result["open_warnings"] = warnings;
            return result;
        }

        private JObject Activate(JObject p)
        {
            var path = Path.GetFullPath(Protocol.Required(p, "document_path"));
            var model = (ModelDoc2)app.GetOpenDocumentByName(path)
                ?? throw new CommandError("document_not_open", "Document is not open in this SOLIDWORKS instance.");
            int errors = 0;
            var activated = (ModelDoc2)app.ActivateDoc3(model.GetTitle(), false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref errors);
            if (activated == null || !string.Equals(activated.GetPathName(), path, StringComparison.OrdinalIgnoreCase))
                throw new CommandError("activate_failed", "SOLIDWORKS did not activate the requested document; error=" + errors);
            if (activated.GetType() != (int)swDocumentTypes_e.swDocDRAWING)
            {
                var requested = Protocol.Required(p, "configuration");
                if (Configuration(activated) != requested && !activated.ShowConfiguration2(requested))
                    throw new CommandError("configuration_missing", "Requested configuration could not be activated.");
            }
            return new JObject { ["document"] = Document(activated), ["errors"] = errors };
        }

        private IEnumerable<DisplayDimension> Dimensions(ModelDoc2 model)
        {
            var seenFeatures = new HashSet<string>(StringComparer.Ordinal);
            IEnumerable<DisplayDimension> Visit(Feature feature)
            {
                if (feature == null || !seenFeatures.Add(feature.Name)) yield break;
                var display = (DisplayDimension)feature.GetFirstDisplayDimension();
                while (display != null) { yield return display; display = (DisplayDimension)feature.GetNextDisplayDimension(display); }
                var child = (Feature)feature.GetFirstSubFeature();
                while (child != null) { foreach (var item in Visit(child)) yield return item; child = (Feature)child.GetNextSubFeature(); }
            }
            var current = (Feature)model.FirstFeature();
            while (current != null) { foreach (var item in Visit(current)) yield return item; current = (Feature)current.GetNextFeature(); }
        }

        private static double Value(Dimension dimension, string configuration)
        {
            var values = Items(dimension.GetSystemValue3((int)swInConfigurationOpts_e.swSpecifyConfiguration, new[] { configuration })).ToArray();
            if (values.Length != 1) throw new CommandError("unresolved_dimension", "Dimension did not return exactly one configuration value.");
            return Convert.ToDouble(values[0]);
        }

        private static string BlockReason(ModelDoc2 model, Dimension dimension)
        {
            if (dimension.ReadOnly) return "read_only_dimension";
            if (dimension.DrivenState != (int)swDimensionDrivenState_e.swDimensionDriving) return "not_driving_dimension";
            if (model.GetDesignTable() != null) return "design_table_present";
            var equations = (EquationMgr)model.GetEquationMgr();
            // Until per-parameter equation dependencies are mapped, equation-bearing models stay read-only.
            if (equations != null && equations.GetCount() > 0) return "equations_present";
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART) return "part_only";
            var bodies = Items(((PartDoc)model).GetBodies2((int)swBodyType_e.swSolidBody, false)).ToArray();
            if (bodies.Length != 1) return "single_solid_body_required";
            return null;
        }

        private JArray Parameters(ModelDoc2 model)
        {
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART) throw new CommandError("unsupported_document", "Parameter inventory supports part documents.");
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var result = new JArray();
            foreach (var display in Dimensions(model))
            {
                var dimension = (Dimension)display.GetDimension2(0);
                if (dimension == null || !seen.Add(dimension.FullName)) continue;
                var reason = BlockReason(model, dimension);
                var supportedType = display.Type2 == (int)swDimensionType_e.swLinearDimension || display.Type2 == (int)swDimensionType_e.swDiameterDimension;
                if (!supportedType) reason = "only_linear_or_diameter";
                result.Add(new JObject { ["name"] = dimension.FullName, ["value"] = Value(dimension, Configuration(model)),
                    ["unit"] = supportedType ? "m" : "system", ["display_type"] = display.Type2,
                    ["read_only"] = dimension.ReadOnly, ["driven_state"] = dimension.DrivenState,
                    ["writable"] = reason == null, ["block_reason"] = reason,
                    ["engineering_role"] = "unmapped", ["persistent_reference"] = Persistent(model, dimension) });
            }
            return result;
        }

        private static string Persistent(ModelDoc2 model, object value)
        {
            var bytes = model.Extension.GetPersistReference3(value) as byte[];
            return bytes == null || bytes.Length == 0 ? null : Convert.ToBase64String(bytes);
        }

        private JObject Change(JObject p)
        {
            var model = Bound(p, true);
            var name = Protocol.Required(p, "parameter_name");
            var configuration = Protocol.Required(p, "configuration");
            var expected = Protocol.Number(p, "expected_value");
            var target = Protocol.Number(p, "value");
            if (target <= 0) throw new CommandError("invalid_value", "Length must be positive, in meters.");
            var display = Dimensions(model).FirstOrDefault(d => ((Dimension)d.GetDimension2(0))?.FullName == name)
                ?? throw new CommandError("unknown_parameter", "Select a parameter returned by parameters.list.");
            var dimension = (Dimension)display.GetDimension2(0);
            var reason = BlockReason(model, dimension);
            if (reason != null) throw new CommandError("unsupported_parameter", reason);
            if (display.Type2 != (int)swDimensionType_e.swLinearDimension && display.Type2 != (int)swDimensionType_e.swDiameterDimension)
                throw new CommandError("unsupported_parameter", "Only linear and diameter dimensions are currently writable.");
            var before = Value(dimension, configuration);
            if (Math.Abs(before - expected) > 1e-10) throw new CommandError("stale_parameter", "Parameter value changed since review.");
            var undoFinished = false;
            var status = -1;
            var rebuilt = false;
            model.Extension.StartRecordingUndoObject();
            try
            {
                nativeMutationStarted = true;
                status = dimension.SetSystemValue3(target, (int)swSetValueInConfiguration_e.swSetValue_InSpecificConfigurations, new[] { configuration });
                rebuilt = model.EditRebuild3();
            }
            finally { undoFinished = model.Extension.FinishRecordingUndoObject2("Gongke: " + name, false); }
            var actual = Value(dimension, configuration);
            var matches = Math.Abs(actual - target) <= 1e-10;
            return new JObject { ["operation_id"] = (string)p["operation_id"], ["before"] = before, ["requested"] = target,
                ["actual"] = actual, ["unit"] = "m", ["set_status"] = status, ["rebuilt"] = rebuilt,
                ["readback_matches"] = matches, ["undo_recorded"] = undoFinished,
                ["status"] = status == (int)swSetValueReturnStatus_e.swSetValue_Successful && rebuilt && matches ? "applied" : "needs_review",
                ["document"] = Document(model), ["saved"] = false };
        }

        private JArray Selection(ModelDoc2 model)
        {
            var result = new JArray();
            var manager = (SelectionMgr)model.SelectionManager;
            for (var i = 1; i <= manager.GetSelectedObjectCount2(-1); i++)
                result.Add(new JObject { ["type"] = manager.GetSelectedObjectType3(i, -1),
                    ["persistent_reference"] = Persistent(model, manager.GetSelectedObject6(i, -1)) });
            return result;
        }

        private JObject Select(JObject p)
        {
            var model = Bound(p);
            RequireRevision(model, p);
            var reference = Convert.FromBase64String(Protocol.Required(p, "persistent_reference"));
            var value = model.Extension.GetObjectByPersistReference3(reference, out var state);
            if (value == null || state != 0) throw new CommandError("selection_missing", "Persistent reference no longer resolves.");
            var selected = model.Extension.MultiSelect2(new[] { value }, false, null);
            return new JObject { ["selected"] = selected == 1, ["selection"] = Selection(model) };
        }

        private JObject Mesh(ModelDoc2 model)
        {
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART) throw new CommandError("unsupported_document", "Mesh preview supports part documents.");
            var faces = new JArray();
            var count = 0;
            foreach (Body2 body in Items(((PartDoc)model).GetBodies2((int)swBodyType_e.swSolidBody, true)))
                foreach (Face2 face in Items(body.GetFaces()))
                {
                    var vertices = Items(face.GetTessTriangles(true)).Select(Convert.ToDouble).ToArray();
                    count += vertices.Length / 9;
                    if (count > 100000) throw new CommandError("preview_too_large", "Preview exceeds 100000 triangles.");
                    faces.Add(new JObject { ["persistent_reference"] = Persistent(model, face), ["positions"] = new JArray(vertices) });
                }
            var result = new JObject { ["unit"] = "m", ["purpose"] = "display_only", ["faces"] = faces, ["document"] = Document(model) };
            if (System.Text.Encoding.UTF8.GetByteCount(result.ToString(Newtonsoft.Json.Formatting.None)) > 6 * 1024 * 1024)
                throw new CommandError("preview_too_large", "Preview exceeds the 6 MiB transport budget.");
            return result;
        }

        private JObject Drawing(ModelDoc2 model)
        {
            if (model.GetType() != (int)swDocumentTypes_e.swDocDRAWING) throw new CommandError("unsupported_document", "Activate a drawing document.");
            var sheets = new JArray();
            foreach (var raw in Items(((DrawingDoc)model).GetViews()))
            {
                var views = Items(raw).Cast<View>().ToArray();
                var records = new JArray();
                foreach (var view in views.Skip(1))
                {
                    var dimensions = new JArray();
                    var display = (DisplayDimension)view.GetFirstDisplayDimension5();
                    while (display != null)
                    {
                        var dimension = (Dimension)display.GetDimension2(0);
                        var annotation = (Annotation)display.GetAnnotation();
                        dimensions.Add(new JObject { ["name"] = dimension?.FullName,
                            ["dangling"] = annotation?.IsDangling(), ["display_type"] = display.Type2,
                            ["override"] = display.GetOverride(), ["override_value"] = display.GetOverrideValue(),
                            ["persistent_reference"] = Persistent(model, display) });
                        display = (DisplayDimension)display.GetNext5();
                    }
                    records.Add(new JObject { ["name"] = view.Name, ["model_path"] = view.GetReferencedModelName(),
                        ["loaded_model_path"] = view.ReferencedDocument?.GetPathName(),
                        ["configuration"] = view.ReferencedConfiguration, ["dimensions"] = dimensions });
                }
                sheets.Add(new JObject { ["name"] = views.FirstOrDefault()?.Name, ["views"] = records });
            }
            return new JObject { ["document"] = Document(model), ["sheets"] = sheets,
                ["active_sheet"] = ((Sheet)((DrawingDoc)model).GetCurrentSheet()).GetName(),
                ["engineering_acceptance"] = "not_assessed" };
        }

        private JObject UpdateDrawing(JObject p)
        {
            var model = Bound(p, true);
            if (model.GetType() != (int)swDocumentTypes_e.swDocDRAWING) throw new CommandError("unsupported_document", "Activate the drawing to update.");
            nativeMutationStarted = true;
            var rebuilt = model.ForceRebuild3(false);
            var inspection = Drawing(model);
            inspection["rebuilt"] = rebuilt;
            inspection["saved"] = false;
            return inspection;
        }

        private JObject SaveCopy(JObject p)
        {
            var model = Bound(p, true);
            if (model.GetType() == (int)swDocumentTypes_e.swDocDRAWING) return SaveDrawingCopy(model, p);
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART) throw new CommandError("unsupported_document", "Copy supports one part or a drawing referring to one part and configuration.");
            RequireIndependentPart(model);
            var output = Protocol.NewOutputPath(p, ".sldprt");
            int errors = 0, warnings = 0;
            nativeMutationStarted = true;
            var ok = model.Extension.SaveAs3(output, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent | (int)swSaveAsOptions_e.swSaveAsOptions_Copy,
                null, null, ref errors, ref warnings);
            return Saved(model, output, ok, errors, warnings);
        }

        private JObject Save(JObject p)
        {
            var model = Bound(p, true);
            int errors = 0, warnings = 0;
            nativeMutationStarted = true;
            var ok = model.Save3((int)swSaveAsOptions_e.swSaveAsOptions_Silent, ref errors, ref warnings);
            return Saved(model, model.GetPathName(), ok, errors, warnings);
        }

        private static JObject Saved(ModelDoc2 model, string path, bool ok, int errors, int warnings) => new JObject {
            ["status"] = ok && errors == 0 && File.Exists(path) ? "saved" : "needs_review",
            ["path"] = path, ["file_exists"] = File.Exists(path), ["errors"] = errors, ["warnings"] = warnings,
            ["document"] = Document(model), ["reopen_verified"] = false };

        private JObject ExportDrawing(JObject p)
        {
            var model = Bound(p, true);
            if (model.GetType() != (int)swDocumentTypes_e.swDocDRAWING) throw new CommandError("unsupported_document", "DXF export requires an active drawing.");
            var drawing = (DrawingDoc)model;
            var sheet = (Sheet)drawing.GetCurrentSheet();
            if (Protocol.Required(p, "sheet") != sheet.GetName()) throw new CommandError("sheet_changed", "Activate the reviewed drawing sheet before export.");
            var path = Protocol.NewOutputPath(p, ".dxf");
            // Export only the reviewed active sheet. Restore the user's global setting even on failure.
            var preference = (int)swUserPreferenceIntegerValue_e.swDxfMultiSheetOption;
            var previous = app.GetUserPreferenceIntegerValue(preference);
            try
            {
                if (!app.SetUserPreferenceIntegerValue(preference, (int)swDxfMultisheet_e.swDxfActiveSheetOnly))
                    throw new CommandError("export_setting_failed", "Cannot restrict DXF export to the active sheet.");
                model.ClearSelection2(true);
                int errors = 0, warnings = 0;
                nativeMutationStarted = true;
                var ok = model.Extension.SaveAs3(path, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                    (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null, null, ref errors, ref warnings);
                var result = Saved(model, path, ok, errors, warnings);
                result["sheet"] = sheet.GetName();
                result["unit_verification"] = "requires_dxf_inspection";
                return result;
            }
            finally
            {
                if (!app.SetUserPreferenceIntegerValue(preference, previous))
                    throw new CommandError("export_preference_restore_failed", "DXF output may exist, but the previous multi-sheet export preference could not be restored. Check SOLIDWORKS export settings before continuing.", "unknown");
            }
        }
    }
}
