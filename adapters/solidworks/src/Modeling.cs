using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace Gongke.SolidWorks
{
    internal sealed partial class HostOperations
    {
        internal static readonly string[] ModelingWrites = { "model.new", "model.copy", "model.body", "model.sketch", "model.feature",
            "model.feature_edit", "model.feature_delete", "model.rebuild", "model.save" };
        // SOLIDWORKS 无空 Body：预留仅限当前打开文档，首个非合并凸台创建真正 Body2。
        private readonly Dictionary<string, (ModelDoc2 Model, string Name)> pendingBodies = new Dictionary<string, (ModelDoc2, string)>();

        private ModelDoc2 ModelingBound(JObject p, bool requireCopy = true)
        {
            var docs = OpenInspectionDocuments();
            var reference = p["document"] as JObject ?? throw new CommandError("invalid_request", "需要 document");
            var model = docs.SingleOrDefault(d => inspectionDocuments[d] == (string)reference["document_id"])
                ?? throw new CommandError("document_missing", "文档已关闭");
            if (!JToken.DeepEquals(InspectionRef(model), reference)) throw new CommandError("stale_document", "文档修订、配置或宿主实例已改变");
            if (model != app.IActiveDoc2) throw new CommandError("inactive_document", "请先激活指定零件");
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART || model.IsOpenedReadOnly() || model.IsOpenedViewOnly())
                throw new CommandError("part_required", "需要完整加载的可编辑零件");
            if (model.SketchManager.ActiveSketch != null) throw new CommandError("edit_in_progress", "请先退出当前草图编辑");
            if (requireCopy && !workingCopies.Contains(model.GetPathName())) throw new CommandError("working_copy_required", "只写本宿主会话创建的工作副本");
            return model;
        }

        private T ModelingEntity<T>(ModelDoc2 model, string reference) where T : class
        {
            var value = model.Extension.GetObjectByPersistReference3(Convert.FromBase64String(reference), out var error) as T;
            if (error != 0 || value == null) throw new CommandError("entity_missing", "引用已失效或对象类型不符");
            return value;
        }
        private Body2 ModelingBody(ModelDoc2 model, string reference)
        {
            if (pendingBodies.TryGetValue(reference, out var owner))
            {
                if (owner.Model != model) throw new CommandError("wrong_body", "预留 Body 不属于此文档");
                return null;
            }
            var body = ModelingEntity<Body2>(model, reference);
            if (!InspectionBodies(model).Contains(body)) throw new CommandError("wrong_body", "实体不属于当前零件");
            return body;
        }
        private JObject ReserveBody(ModelDoc2 model, string name)
        {
            var id = "pending:" + Guid.NewGuid().ToString("D");
            ModelingName(model, name);
            pendingBodies.Add(id, (model, name));
            return new JObject { ["body_ref"] = id, ["body_state"] = "pending_first_feature" };
        }
        private static void ModelingName(ModelDoc2 model, string name)
        {
            if (!Regex.IsMatch(name, "^[A-Za-z][A-Za-z0-9_]{0,79}$") || ModelingFeatures(model).Any(f => f.Name == name))
                throw new CommandError("invalid_name", "特征名必须是未使用的 ASCII 标识符");
        }
        private static void ModelingSelect(ModelDoc2 model, object value, int mark = 0, bool append = false)
        {
            if (!append) model.ClearSelection2(true);
            // SOLIDWORKS 2023 SP0.1 实机：MultiSelect2 对基准面、草图返回 0；按特征实际名称 SelectByID2 可选中。
            if (value is Feature feature)
            {
                var typeName = feature.GetTypeName2();
                var selectType = typeName == "RefPlane" ? "PLANE"
                    : typeName == "ProfileFeature" || typeName == "3DProfileFeature" ? "SKETCH" : null;
                if (selectType != null && model.Extension.SelectByID2(feature.Name, selectType, 0, 0, 0, append, mark, null, 0)) return;
            }
            var data = ((SelectionMgr)model.SelectionManager).CreateSelectData(); data.Mark = mark;
            if (model.Extension.MultiSelect2(new[] { value }, append, data) != 1)
                throw new CommandError("selection_failed", "宿主未选中指定原生引用");
        }
        private JObject ModelingOperation(JObject p)
        {
            var row = journal.Get(Protocol.OperationId(p));
            return row == null ? new JObject { ["state"] = "not_found", ["outcome"] = "unknown", ["host_instance"] = session } :
                new JObject { ["state"] = row["state"], ["host_instance"] = row["session_id"], ["fingerprint"] = row["fingerprint"],
                    ["operation_id"] = row["operation_id"], ["outcome"] = row["outcome"],
                    ["result"] = row["response"]?["result"] ?? new JObject { ["error"] = row["response"]?["error"] } };
        }
        // 用户配置的默认零件模板优先；未配置时使用 ProgramData 下随 SOLIDWORKS 安装的零件模板。
        private string PartTemplate()
        {
            var configured = app.GetUserPreferenceStringValue((int)swUserPreferenceStringValue_e.swDefaultTemplatePart);
            if (File.Exists(configured)) return configured;
            var root = Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.CommonApplicationData), "SOLIDWORKS");
            if (!Directory.Exists(root)) return null;
            var templates = Directory.GetFiles(root, "*.prtdot", SearchOption.AllDirectories);
            return templates.FirstOrDefault(t => Path.GetFileName(t).Equals("gb_part.prtdot", StringComparison.OrdinalIgnoreCase)) ?? templates.FirstOrDefault();
        }
        private JObject ModelNew(JObject p)
        {
            if (Protocol.Required(p, "host_instance") != session) throw new CommandError("stale_session", "宿主实例已改变");
            var path = Protocol.NewOutputPath(new JObject { ["output_path"] = p["path"] }, ".sldprt");
            RequireNewDocumentNames(path);
            var template = PartTemplate() ?? throw new CommandError("template_missing", "请在 SOLIDWORKS“选项 → 系统选项 → 默认模板”中设置零件模板");
            nativeMutationStarted = true;
            var model = (ModelDoc2)app.NewDocument(template, 0, 0, 0);
            if (model == null) throw new CommandError("new_document_failed", "NewDocument 返回空");
            nativeEffectObserved = true;
            int errors = 0, warnings = 0;
            model.ClearSelection2(true);
            var ok = model.Extension.SaveAs3(path, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null, null, ref errors, ref warnings);
            if (!ok || errors != 0 || !File.Exists(path)) throw new CommandError("save_failed", "SaveAs3 errors="+errors+", warnings="+warnings);
            workingCopies.Add(path);
            OpenInspectionDocuments();
            var result = ReserveBody(model, Protocol.Required(p, "name"));
            result["path"] = path; result["file_exists"] = true; result["warnings"] = warnings;
            result["document"] = InspectionRef(model); result["outcome"] = "committed";
            return result;
        }
        private JObject ModelCopy(JObject p)
        {
            var model = ModelingBound(p, false);
            var copied = SavePartCopy(model, new JObject { ["output_path"] = p["path"] });
            if ((string)copied["status"] != "saved") return copied;
            OpenInspectionDocuments();
            copied["document"] = InspectionRef(app.IActiveDoc2);
            copied["outcome"] = "committed";
            copied["bodies"] = new JArray(InspectionBodies(app.IActiveDoc2).Select(b => RequiredPersistent(app.IActiveDoc2, b)));
            return copied;
        }

        private JObject ModelingDispatch(string method, JObject p)
        {
            if (method == "model.operation") return ModelingOperation(p);
            if (method == "model.new") return ModelNew(p);
            if (method == "model.copy") return ModelCopy(p);
            var model = ModelingBound(p);
            if (method == "model.body")
            {
                var body = ReserveBody(model, Protocol.Required(p, "name")); body["document"] = InspectionRef(model); body["outcome"] = "committed"; return body;
            }
            if (method == "model.save")
            {
                int errors = 0, warnings = 0; nativeMutationStarted = true;
                if (!model.Save3((int)swSaveAsOptions_e.swSaveAsOptions_Silent, ref errors, ref warnings) || errors != 0)
                    throw new CommandError("save_failed", "Save3 errors="+errors+", warnings="+warnings);
                nativeEffectObserved = true;
                return new JObject { ["document"] = InspectionRef(model), ["path"] = model.GetPathName(),
                    ["file_exists"] = File.Exists(model.GetPathName()), ["outcome"] = "committed", ["warnings"] = warnings };
            }
            // 一个工具一个原生 Undo 对象；失败不伪称回滚，现有 journal 记录 unknown/needs_review。
            model.Extension.StartRecordingUndoObject();
            JObject result;
            bool undoRecorded;
            try
            {
                switch (method)
                {
                    case "model.sketch": result = ModelSketch(model, p); break;
                    case "model.feature": result = ModelFeature(model, p); break;
                    case "model.feature_edit": result = ModelEdit(model, p); break;
                    case "model.feature_delete": result = ModelDelete(model, p); break;
                    case "model.rebuild": result = new JObject(); break;
                    default: throw new CommandError("unknown_method", method);
                }
                nativeMutationStarted = true;
                var rebuilt = model.EditRebuild3();
                var diagnostics = ModelingDiagnostics(model);
                if (!rebuilt || diagnostics.OfType<JObject>().Any(d => (string)d["severity"] == "error"))
                    throw new CommandError("rebuild_failed", diagnostics.ToString(Newtonsoft.Json.Formatting.None), "needs_review");
                nativeEffectObserved = true;
                result["diagnostics"] = diagnostics;
                if (method == "model.feature") { model.ViewZoomtofit2(); model.GraphicsRedraw2(); }
            }
            finally
            {
                model.ClearSelection2(true);
                // SOLIDWORKS 2023 SP0.1 实机上恒返回 false，而几何已正确写入；不作为失败，如实报告撤销分组是否建立。
                undoRecorded = model.Extension.FinishRecordingUndoObject2("构想引擎原生建模", false);
            }
            result["undo_recorded"] = undoRecorded;
            result["document"] = InspectionRef(model); result["outcome"] = "committed";
            return result;
        }
        private static IEnumerable<Feature> ModelingFeatures(ModelDoc2 model)
        {
            var seen = new HashSet<string>();
            IEnumerable<Feature> Visit(Feature feature)
            {
                if (!seen.Add(feature.Name)) yield break;
                yield return feature;
                var child = (Feature)feature.GetFirstSubFeature();
                while (child != null) { foreach (var item in Visit(child)) yield return item; child = (Feature)child.GetNextSubFeature(); }
            }
            var current = (Feature)model.FirstFeature();
            while (current != null) { foreach (var item in Visit(current)) yield return item; current = (Feature)current.GetNextFeature(); }
        }
        private JArray ModelingDiagnostics(ModelDoc2 model)
        {
            var rows = new JArray();
            foreach (var f in ModelingFeatures(model))
            {
                int code = f.GetErrorCode2(out var warning);
                if (code != 0) rows.Add(new JObject { ["native_ref"] = RequiredPersistent(model, f), ["error_code"] = code, ["severity"] = warning ? "warning" : "error" });
                if (f.GetSpecificFeature2() is Sketch sketch)
                {
                    var status = (swConstrainedStatus_e)sketch.GetConstrainedStatus();
                    rows.Add(new JObject { ["native_ref"] = RequiredPersistent(model, f), ["solver"] = status.ToString(),
                        ["native_status"] = (int)status, ["fully_constrained"] = status == swConstrainedStatus_e.swFullyConstrained,
                        ["severity"] = status == swConstrainedStatus_e.swFullyConstrained || status == swConstrainedStatus_e.swUnderConstrained ? "info" : "error" });
                }
            }
            return rows;
        }

        private static double[] ModelingNormal(string plane) => plane == "XY" ? new[] { 0.0, 0, 1 } : plane == "XZ" ? new[] { 0.0, -1, 0 } : plane == "YZ" ? new[] { 1.0, 0, 0 } : throw new CommandError("invalid_plane", plane);
        private Feature ModelingPlane(ModelDoc2 model, string plane)
        {
            var n = ModelingNormal(plane);
            // 从官方平面变换匹配原点基准面，不依赖中文/英文名称。
            return ModelingFeatures(model).FirstOrDefault(f => {
                if (!(f.GetSpecificFeature2() is RefPlane rp)) return false;
                var t = D(rp.Transform.ArrayData);
                return Math.Abs(Math.Abs(Dot(t.Skip(6).Take(3).ToArray(), n))-1) < 1e-9 && t.Skip(9).Take(3).All(v => Math.Abs(v) < 1e-9);
            }) ?? throw new CommandError("plane_missing", "模板缺少所需原点基准面");
        }
        private object ModelingSupport(ModelDoc2 model, JObject p)
        {
            if (p["face_ref"] != null)
            {
                var face = ModelingEntity<Face2>(model, (string)p["face_ref"]);
                if (!((Surface)face.GetSurface()).IsPlane()) throw new CommandError("planar_face_required", "草图需要平面面");
                return face;
            }
            string plane = Protocol.Required(p, "plane");
            var basis = ModelingPlane(model, plane);
            double offset = (double?)p["offset"] ?? 0;
            if (offset == 0) return basis;
            ModelingSelect(model, basis);
            var transform = D(((RefPlane)basis.GetSpecificFeature2()).Transform.ArrayData);
            bool reverse = offset * Dot(transform.Skip(6).Take(3).ToArray(), ModelingNormal(plane)) < 0;
            int flags = (int)swRefPlaneReferenceConstraints_e.swRefPlaneReferenceConstraint_Distance;
            if (reverse) flags |= (int)swRefPlaneReferenceConstraints_e.swRefPlaneReferenceConstraint_OptionFlip;
            nativeMutationStarted = true;
            return model.FeatureManager.InsertRefPlane(flags, Math.Abs(offset), 0, 0, 0, 0)
                ?? throw new CommandError("plane_failed", "InsertRefPlane 返回空");
        }
        private JObject ModelingFrame(Sketch sketch)
        {
            var t = D(((MathTransform)sketch.ModelToSketchTransform.Inverse()).ArrayData);
            return new JObject { ["origin"] = new JArray(t.Skip(9).Take(3)), ["u"] = new JArray(t.Take(3)),
                ["v"] = new JArray(t.Skip(3).Take(3)), ["normal"] = new JArray(t.Skip(6).Take(3)) };
        }
        private static object SketchEntity(SketchSegment[] segments, JObject e)
        {
            int index = (int)e["geometry"];
            if (index < 0 || index >= segments.Length) throw new CommandError("geometry_missing", "草图索引越界");
            var s = segments[index]; string point = (string)e["point"] ?? "whole";
            if (point == "whole") return s;
            if (s is SketchLine line && point != "center") return point == "start" ? line.GetStartPoint2() : line.GetEndPoint2();
            if (s is SketchArc arc) return point == "center" ? arc.GetCenterPoint2() : point == "start" ? arc.GetStartPoint2() : arc.GetEndPoint2();
            throw new CommandError("point_unavailable", "此几何不支持指定端点");
        }
        private void SketchConstraint(ModelDoc2 model, Sketch sketch, SketchSegment[] segments, JObject c)
        {
            string kind = Protocol.Required(c, "kind");
            var entities = ((JArray)c["entities"]).OfType<JObject>().Select(e => SketchEntity(segments, e)).ToArray();
            var geometric = new Dictionary<string, swConstraintType_e> {
                ["horizontal"] = swConstraintType_e.swConstraintType_HORIZONTAL, ["vertical"] = swConstraintType_e.swConstraintType_VERTICAL,
                ["coincident"] = swConstraintType_e.swConstraintType_COINCIDENT, ["tangent"] = swConstraintType_e.swConstraintType_TANGENT,
                ["parallel"] = swConstraintType_e.swConstraintType_PARALLEL, ["perpendicular"] = swConstraintType_e.swConstraintType_PERPENDICULAR,
                ["equal"] = swConstraintType_e.swConstraintType_SAMELENGTH, ["fixed"] = swConstraintType_e.swConstraintType_FIXED };
            if (geometric.TryGetValue(kind, out var relation))
            {
                if (entities.Length == 2 && entities.All(e => e is SketchPoint))
                {
                    if (kind == "horizontal") relation = swConstraintType_e.swConstraintType_HORIZPOINTS;
                    if (kind == "vertical") relation = swConstraintType_e.swConstraintType_VERTPOINTS;
                }
                if (sketch.RelationManager.AddRelation(entities, (int)relation) == null)
                    throw new CommandError("constraint_failed", "AddRelation 返回空："+kind);
                return;
            }
            model.ClearSelection2(true);
            foreach (var e in entities) ModelingSelect(model, e, 0, true);
            // 原点坐标尺寸需要明确选择草图原点，不依靠点击位置猜测。
            if (entities.Length == 1 && entities[0] is SketchPoint && (kind == "distance_x" || kind == "distance_y" || kind == "distance"))
            {
                var origin = Items(sketch.GetSketchPoints2()).Cast<SketchPoint>().FirstOrDefault(pt => pt.Type == (int)swSketchPointType_e.swSketchPointType_Origin);
                if (origin == null) throw new CommandError("origin_unavailable", "草图原点不可选，请使用两点距离");
                ModelingSelect(model, origin, 0, true);
            }
            DisplayDimension display;
            switch (kind)
            {
                case "distance_x": display = (DisplayDimension)model.AddHorizontalDimension2(.01, .01, 0); break;
                case "distance_y": display = (DisplayDimension)model.AddVerticalDimension2(.01, .01, 0); break;
                case "diameter": display = (DisplayDimension)model.AddDiameterDimension2(.01, .01, 0); break;
                case "radius": display = (DisplayDimension)model.AddRadialDimension2(.01, .01, 0); break;
                case "distance": case "angle": display = (DisplayDimension)model.AddDimension2(.01, .01, 0); break;
                default: throw new CommandError("unknown_constraint", kind);
            }
            if (display == null) throw new CommandError("dimension_failed", "宿主未生成约束尺寸："+kind);
            var expectedType = kind == "angle" ? swDimensionType_e.swAngularDimension : kind == "diameter" ? swDimensionType_e.swDiameterDimension :
                kind == "radius" ? swDimensionType_e.swRadialDimension : swDimensionType_e.swLinearDimension;
            if (display.Type2 != (int)expectedType) throw new CommandError("dimension_type_mismatch", "宿主生成的尺寸类型与请求不符");
            var dimension = (Dimension)display.GetDimension2(0);
            if (c["name"] != null) dimension.Name = Protocol.Required(c, "name");
            int code = dimension.SetSystemValue3(Protocol.Number(c, "value"), (int)swSetValueInConfiguration_e.swSetValue_InThisConfiguration, null);
            if (code != (int)swSetValueReturnStatus_e.swSetValue_Successful) throw new CommandError("dimension_failed", "SetSystemValue3="+code);
        }
        private static SketchSegment[] ModelingSegments(Sketch sketch) => Items(sketch.GetSketchSegments()).Cast<SketchSegment>()
            .OrderBy(s => D(s.GetID())[0]).ThenBy(s => D(s.GetID())[1]).ToArray();

        private JObject ModelSketch(ModelDoc2 model, JObject p)
        {
            var body = ModelingBody(model, Protocol.Required(p, "body_ref"));
            bool existing = p["sketch_ref"] != null;
            Feature feature = null;
            if (existing)
            {
                if (p["support"] != null || p["name"] != null) throw new CommandError("invalid_request", "追加草图不接受 name/support");
                feature = ModelingEntity<Feature>(model, (string)p["sketch_ref"]);
                if (!(feature.GetSpecificFeature2() is Sketch)) throw new CommandError("sketch_required", "引用不是草图");
                ModelingSelect(model, feature);
            }
            else
            {
                ModelingName(model, Protocol.Required(p, "name"));
                var support = ModelingSupport(model, (JObject)p["support"]);
                if (support is Face2 face && (body == null || face.GetBody() != body))
                    throw new CommandError("wrong_body", "支持面不属于指定 Body");
                ModelingSelect(model, support);
            }
            var manager = model.SketchManager;
            bool add = manager.AddToDB, display = manager.DisplayWhenAdded;
            bool dimensionDialog = app.GetUserPreferenceToggle((int)swUserPreferenceToggle_e.swInputDimValOnCreate);
            nativeMutationStarted = true;
            manager.InsertSketch(true);
            var sketch = manager.ActiveSketch ?? throw new CommandError("sketch_failed", "未进入指定草图");
            try
            {
                app.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swInputDimValOnCreate, false);
                manager.AddToDB = true; manager.DisplayWhenAdded = false;
                var segments = ModelingSegments(sketch).ToList();
                var addedSegments = new List<SketchSegment[]>();
                foreach (JObject g in (JArray)p["geometry"])
                {
                    string kind = Protocol.Required(g, "kind");
                    var a = ((JArray)(g["start"] ?? g["center"])).Select(v => (double)v).ToArray();
                    var b = g["end"] == null ? null : ((JArray)g["end"]).Select(v => (double)v).ToArray();
                    var created = new List<SketchSegment>();
                    if (kind == "rectangle")
                    {
                        var pts = new[] { a, new[] { b[0], a[1] }, b, new[] { a[0], b[1] } };
                        for (int i = 0; i < 4; i++) created.Add(manager.CreateLine(pts[i][0], pts[i][1], 0, pts[(i+1)%4][0], pts[(i+1)%4][1], 0));
                    }
                    else if (kind == "line") created.Add(manager.CreateLine(a[0], a[1], 0, b[0], b[1], 0));
                    else if (kind == "circle") created.Add(manager.CreateCircleByRadius(a[0], a[1], 0, Protocol.Number(g, "radius")));
                    else if (kind == "arc")
                    {
                        var mid = ((JArray)g["mid"]).Select(v => (double)v).ToArray();
                        created.Add(manager.Create3PointArc(a[0], a[1], 0, b[0], b[1], 0, mid[0], mid[1], 0));
                    }
                    else throw new CommandError("unknown_geometry", kind);
                    foreach (var item in created)
                    {
                        if (item == null) throw new CommandError("geometry_failed", "SketchManager 返回空："+kind);
                        item.ConstructionGeometry = (bool?)g["construction"] ?? false;
                        segments.Add(item);
                    }
                    // 不给矩形自动加关系：SOLIDWORKS 2023 SP0.1 实机上此处 AddRelation 会使宿主崩溃。
                    // 四条线首尾坐标重合即可拉伸；需要约束时由 constraints 显式添加。
                    addedSegments.Add(created.ToArray());
                }
                manager.AddToDB = false;
                foreach (JObject constraint in (JArray)p["constraints"]) SketchConstraint(model, sketch, segments.ToArray(), constraint);
                feature = ModelingFeatures(model).First(f => f.GetSpecificFeature2() is Sketch candidate && candidate == sketch);
                if (!existing) feature.Name = (string)p["name"];
                nativeEffectObserved = true;
                var finalSegments = ModelingSegments(sketch);
                var added = new JArray(addedSegments.Select(group => new JArray(group.Select(s => Array.IndexOf(finalSegments, s)))));
                return new JObject { ["native_ref"] = RequiredPersistent(model, feature), ["sketch_ref"] = RequiredPersistent(model, feature),
                    ["body_ref"] = p["body_ref"], ["added_geometry"] = added, ["frame"] = ModelingFrame(sketch),
                    ["geometry"] = new JArray(finalSegments.Select((s, i) => new JObject { ["index"] = i, ["native_ref"] = RequiredPersistent(model, s) })),
                    ["editable_parameters"] = ModelingParameters(model, feature) };
            }
            finally
            {
                manager.AddToDB = add; manager.DisplayWhenAdded = display;
                app.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swInputDimValOnCreate, dimensionDialog);
                manager.InsertSketch(true);
            }
        }
        private Feature ModelingAxis(ModelDoc2 model, string axis)
        {
            var planes = axis == "X" ? new[] { "XY", "XZ" } : axis == "Y" ? new[] { "YZ", "XY" } : axis == "Z" ? new[] { "XZ", "YZ" } : throw new CommandError("invalid_axis", axis);
            var before = new HashSet<string>(ModelingFeatures(model).Select(f => f.Name));
            ModelingSelect(model, ModelingPlane(model, planes[0]));
            ModelingSelect(model, ModelingPlane(model, planes[1]), 0, true);
            nativeMutationStarted = true;
            if (!model.InsertAxis2(true)) throw new CommandError("axis_failed", "InsertAxis2 返回 false");
            return ModelingFeatures(model).Single(f => !before.Contains(f.Name) && f.GetTypeName2() == "RefAxis");
        }
        private JObject ModelFeature(ModelDoc2 model, JObject p)
        {
            string bodyRef = Protocol.Required(p, "body_ref"), name = Protocol.Required(p, "name");
            var body = ModelingBody(model, bodyRef);
            ModelingName(model, name);
            var data = (JObject)p["feature"]; string kind = Protocol.Required(data, "kind");
            bool reversed = (bool?)data["reversed"] ?? false;
            Feature profile = null;
            Sketch sketch = null;
            if (data["sketch_ref"] != null)
            {
                profile = ModelingEntity<Feature>(model, (string)data["sketch_ref"]);
                sketch = profile.GetSpecificFeature2() as Sketch ?? throw new CommandError("sketch_required", "需要原生草图");
                if (kind == "revolve")
                {
                    ModelingSelect(model, profile); nativeMutationStarted = true;
                    model.SketchManager.InsertSketch(true);
                    SketchSegment line;
                    bool addToDb = model.SketchManager.AddToDB;
                    try
                    {
                        model.SketchManager.AddToDB = true;
                        bool horizontal = (string)data["axis"] == "horizontal";
                        line = model.SketchManager.CreateCenterLine(0, 0, 0, horizontal ? .01 : 0, horizontal ? 0 : .01, 0);
                        if (line == null) throw new CommandError("axis_failed", "CreateCenterLine 返回空");
                        if (sketch.RelationManager.AddRelation(new object[] { line }, (int)swConstraintType_e.swConstraintType_FIXED) == null)
                            throw new CommandError("axis_failed", "无法固定旋转轴");
                    }
                    finally { model.SketchManager.AddToDB = addToDb; model.SketchManager.InsertSketch(true); }
                    ModelingSelect(model, profile);
                    ModelingSelect(model, line, 16, true);
                }
                else ModelingSelect(model, profile);
            }
            else model.ClearSelection2(true);
            if (body == null && kind != "pad" && kind != "revolve") throw new CommandError("body_required", "先用 pad/revolve 创建实体");
            // 切除不预选实体（mark 8）：实机上预选后 FeatureCut4 返回空，改由 UseAutoSelect 选择实体。
            if (body != null && kind == "pad") ModelingSelect(model, body, 8, true);
            nativeMutationStarted = true;
            var fm = model.FeatureManager;
            Feature feature;
            switch (kind)
            {
                case "pad":
                    feature = fm.FeatureExtrusion3(true, false, reversed, 0, 0, Protocol.Number(data, "length"), 0,
                        false, false, false, false, 0, 0, false, false, false, false, body != null, body != null, false, 0, 0, false);
                    break;
                case "hole":
                    // 直孔采用可编辑圆草图 + 原生切除；不虚构 Hole Wizard 的标准/螺纹参数。
                    var circles = Items(sketch.GetSketchSegments()).Cast<SketchSegment>().Where(s => !s.ConstructionGeometry).ToArray();
                    if (circles.Length == 0 || circles.Any(s => !(s is SketchArc a) || a.IsCircle() == 0 || Math.Abs(2*a.GetRadius()-Protocol.Number(data, "diameter")) > 1e-9))
                        throw new CommandError("hole_profile_mismatch", "直孔草图需全圆且直径与 diameter 一致；先修改草图命名尺寸");
                    goto case "pocket";
                case "pocket":
                    bool throughAll = (bool?)data["through_all"] == true;
                    // 贯穿用两侧贯穿，结果与方向无关；实机上仅一个方向参数返回特征，故两个方向各试一次。盲切按给定深度和方向，不改语义。
                    Feature Cut(int end, bool direction, double depth) => fm.FeatureCut4(true, false, direction, end, 0, depth, 0,
                        false, false, false, false, 0, 0, false, false, false, false, false, true, true, false, false, false, 0, 0, false, false);
                    feature = throughAll
                        ? Cut((int)swEndConditions_e.swEndCondThroughAllBoth, reversed, 0) ?? Cut((int)swEndConditions_e.swEndCondThroughAllBoth, !reversed, 0)
                        : Cut((int)swEndConditions_e.swEndCondBlind, reversed, Protocol.Number(data, "length"));
                    break;
                case "revolve":
                    feature = fm.FeatureRevolve2(true, true, false, false, reversed, false, 0, 0, Protocol.Number(data, "angle"), 0,
                        false, false, 0, 0, 0, 0, 0, body != null, body != null, false);
                    break;
                case "fillet": case "chamfer":
                    model.ClearSelection2(true);
                    foreach (string edgeRef in (JArray)data["edges"])
                    {
                        var edge = ModelingEntity<Edge>(model, edgeRef);
                        if (edge.GetBody() != body) throw new CommandError("wrong_body", "边不属于目标实体");
                        ModelingSelect(model, edge, 0, true);
                    }
                    feature = kind == "fillet" ? (Feature)fm.FeatureFillet3((int)swFeatureFilletOptions_e.swFeatureFilletUniformRadius,
                        Protocol.Number(data, "radius"), 0, 0, (int)swFeatureFilletType_e.swFeatureFilletType_Simple, 0, 0, null, null, null, null, null, null, null) :
                        fm.InsertFeatureChamfer(0, (int)swChamferType_e.swChamferAngleDistance, Protocol.Number(data, "size"), Math.PI/4, 0, 0, 0, 0);
                    break;
                case "mirror": case "linear_pattern": case "polar_pattern":
                    object direction = kind == "mirror" ? (object)ModelingPlane(model, (string)data["plane"]) : ModelingAxis(model, (string)data["axis"]);
                    bool axisReversed = false;
                    if (direction is Feature axisFeature && axisFeature.GetSpecificFeature2() is RefAxis nativeAxis)
                    {
                        var points = D(nativeAxis.GetRefAxisParams());
                        int component = (string)data["axis"] == "X" ? 0 : (string)data["axis"] == "Y" ? 1 : 2;
                        axisReversed = points[component+3] < points[component];
                    }
                    model.ClearSelection2(true);
                    foreach (string featureRef in (JArray)data["features"])
                    {
                        var seed = ModelingEntity<Feature>(model, featureRef);
                        if (!Items(body.GetFeatures()).Contains(seed)) throw new CommandError("wrong_body", "种子特征不属于目标实体");
                        ModelingSelect(model, seed, kind == "mirror" ? 1 : 4, true);
                    }
                    ModelingSelect(model, direction, kind == "mirror" ? 2 : 1, true);
                    if (kind == "mirror") feature = fm.InsertMirrorFeature2(false, false, false, false, (int)swFeatureScope_e.swFeatureScope_SelectedBodiesWithAutoSelect);
                    else if (kind == "linear_pattern")
                    {
                        var pattern = (LinearPatternFeatureData)fm.CreateDefinition((int)swFeatureNameID_e.swFmLPattern);
                        pattern.D1ReverseDirection = axisReversed;
                        pattern.D1EndCondition = 0; pattern.D1Spacing = Protocol.Number(data, "spacing");
                        pattern.D1TotalInstances = (int)data["count"]; pattern.D2TotalInstances = 1;
                        pattern.GeometryPattern = false; pattern.VarySketch = false;
                        feature = (Feature)fm.CreateFeature(pattern);
                    }
                    else
                    {
                        var pattern = (CircularPatternFeatureData)fm.CreateDefinition((int)swFeatureNameID_e.swFmCirPattern);
                        pattern.ReverseDirection = axisReversed;
                        // API Spacing 是相邻角；关闭 EqualSpacing 后明确给出，不依赖 UI 的整圆解释。
                        double sweep = Protocol.Number(data, "angle");
                        int count = (int)data["count"];
                        pattern.EqualSpacing = false;
                        pattern.Spacing = sweep / (Math.Abs(sweep-2*Math.PI) < 1e-10 ? count : count-1);
                        pattern.TotalInstances = (int)data["count"]; pattern.GeometryPattern = false;
                        feature = (Feature)fm.CreateFeature(pattern);
                    }
                    break;
                default: throw new CommandError("unknown_feature", kind);
            }
            if (feature == null) throw new CommandError("feature_failed", "FeatureManager 返回空："+kind);
            nativeEffectObserved = true;
            feature.Name = name;
            var faces = Items(feature.GetFaces()).Cast<Face2>().ToArray();
            var outputBody = faces.FirstOrDefault()?.GetBody() as Body2;
            if (outputBody == null) throw new CommandError("body_unavailable", "新特征未返回实体");
            if (pendingBodies.TryGetValue(bodyRef, out var pending))
            { outputBody.Name = pending.Name; pendingBodies.Remove(bodyRef); }
            string reference = RequiredPersistent(model, feature), bodyReference = RequiredPersistent(model, outputBody);
            return new JObject { ["feature_ref"] = reference, ["native_ref"] = reference, ["body_ref"] = bodyReference, ["object_ref"] = bodyReference,
                ["native_type"] = feature.GetTypeName2(), ["editable_parameters"] = ModelingParameters(model, feature) };
        }
        private static bool ModelingDimensionWritable(ModelDoc2 model, Dimension value)
        {
            // 尺寸保护不沿用旧轴工具的“必须恰好一个实体”限制；空草图也可编辑。
            var equations = (EquationMgr)model.GetEquationMgr();
            return !value.ReadOnly && value.DrivenState == (int)swDimensionDrivenState_e.swDimensionDriving
                && model.GetDesignTable() == null && (equations == null || equations.GetCount() == 0);
        }
        private JArray ModelingParameters(ModelDoc2 model, Feature feature)
        {
            var result = new JArray();
            var dim = (DisplayDimension)feature.GetFirstDisplayDimension();
            while (dim != null)
            {
                var value = (Dimension)dim.GetDimension2(0);
                var type = (swDimensionType_e)dim.Type2;
                string unit = type == swDimensionType_e.swAngularDimension ? "rad" :
                    type == swDimensionType_e.swLinearDimension || type == swDimensionType_e.swDiameterDimension || type == swDimensionType_e.swRadialDimension ? "m" : null;
                if (value != null && unit != null && ModelingDimensionWritable(model, value))
                    result.Add(new JObject { ["name"] = value.FullName, ["value"] = Value(value, Configuration(model)), ["unit"] = unit });
                dim = (DisplayDimension)feature.GetNextDisplayDimension(dim);
            }
            var data = feature.GetDefinition();
            if (data is LinearPatternFeatureData linear)
                result.Add(new JObject { ["name"] = "Occurrences", ["value"] = linear.D1TotalInstances, ["unit"] = "1" });
            if (data is CircularPatternFeatureData circular)
                result.Add(new JObject { ["name"] = "Occurrences", ["value"] = circular.TotalInstances, ["unit"] = "1" });
            return result;
        }
        private JObject ModelEdit(ModelDoc2 model, JObject p)
        {
            var feature = ModelingEntity<Feature>(model, Protocol.Required(p, "feature_ref"));
            string name = Protocol.Required(p, "parameter");
            if (!ModelingParameters(model, feature).OfType<JObject>().Any(r => (string)r["name"] == name))
                throw new CommandError("parameter_not_writable", "只允许修改此特征 editable_parameters 中的尺寸");
            if (name == "Occurrences")
            {
                double value = Protocol.Number(p, "value");
                if (value < 2 || value != Math.Truncate(value) || value > int.MaxValue)
                    throw new CommandError("invalid_count", "阵列数量必须为至少2的整数");
                var data = feature.GetDefinition();
                if (data is LinearPatternFeatureData linear)
                {
                    if (!linear.AccessSelections(model, null)) throw new CommandError("selection_access_failed", "无法编辑阵列引用");
                    bool modified = false;
                    try { nativeMutationStarted = true; linear.D1TotalInstances = (int)value;
                        modified = feature.ModifyDefinition(linear, model, null);
                        if (!modified) throw new CommandError("pattern_edit_failed", "ModifyDefinition 返回 false"); }
                    finally { if (!modified) linear.ReleaseSelectionAccess(); }
                }
                else if (data is CircularPatternFeatureData circular)
                {
                    if (!circular.AccessSelections(model, null)) throw new CommandError("selection_access_failed", "无法编辑阵列引用");
                    bool modified = false;
                    try { nativeMutationStarted = true; circular.TotalInstances = (int)value;
                        modified = feature.ModifyDefinition(circular, model, null);
                        if (!modified) throw new CommandError("pattern_edit_failed", "ModifyDefinition 返回 false"); }
                    finally { if (!modified) circular.ReleaseSelectionAccess(); }
                }
                nativeEffectObserved = true;
                return new JObject { ["feature_ref"] = p["feature_ref"], ["editable_parameters"] = ModelingParameters(model, feature) };
            }
            var dim = (Dimension)model.Parameter(name);
            nativeMutationStarted = true;
            int code = dim.SetSystemValue3(Protocol.Number(p, "value"), (int)swSetValueInConfiguration_e.swSetValue_InThisConfiguration, null);
            if (code != (int)swSetValueReturnStatus_e.swSetValue_Successful) throw new CommandError("dimension_failed", "SetSystemValue3="+code);
            nativeEffectObserved = true;
            return new JObject { ["feature_ref"] = p["feature_ref"], ["editable_parameters"] = ModelingParameters(model, feature) };
        }
        private JObject ModelDelete(ModelDoc2 model, JObject p)
        {
            var feature = ModelingEntity<Feature>(model, Protocol.Required(p, "feature_ref"));
            var children = Items(feature.GetChildren()).Cast<Feature>().ToArray();
            if (children.Length != 0) throw new CommandError("feature_has_dependents", string.Join(", ", children.Select(c => c.Name)));
            ModelingSelect(model, feature); nativeMutationStarted = true;
            // 0：不选择 DeleteChildren 或 DeleteAbsorbed；不级联删除源草图。
            if (!model.Extension.DeleteSelection2(0)) throw new CommandError("delete_failed", "DeleteSelection2 返回 false");
            nativeEffectObserved = true;
            return new JObject { ["deleted_ref"] = p["feature_ref"] };
        }
    }
}
