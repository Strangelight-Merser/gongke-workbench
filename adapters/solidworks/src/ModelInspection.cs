using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace Gongke.SolidWorks
{
    internal sealed partial class HostOperations
    {
        // 仅保留打开文档的会话身份；不把文件路径或标题当作文档生命期身份。
        private readonly Dictionary<ModelDoc2, string> inspectionDocuments = new Dictionary<ModelDoc2, string>();
        private ModelDoc2[] OpenInspectionDocuments()
        {
            var docs = Items(app.GetDocuments()).Cast<ModelDoc2>().ToArray();
            foreach (var key in inspectionDocuments.Keys.Where(d => !docs.Contains(d)).ToArray()) inspectionDocuments.Remove(key);
            foreach (var doc in docs) if (!inspectionDocuments.ContainsKey(doc)) inspectionDocuments[doc] = Guid.NewGuid().ToString("D");
            return docs;
        }
        private JObject InspectionRef(ModelDoc2 model) => new JObject {
            ["host_instance"] = session, ["document_id"] = inspectionDocuments[model],
            ["revision"] = model.GetUpdateStamp(), ["configuration"] = Configuration(model) ?? ""
        };
        private static Body2[] InspectionBodies(ModelDoc2 model) => model.GetType() == (int)swDocumentTypes_e.swDocPART
            ? Items(((PartDoc)model).GetBodies2((int)swBodyType_e.swAllBodies, false)).Cast<Body2>().ToArray() : new Body2[0];
        private JObject InspectionContext()
        {
            var docs = OpenInspectionDocuments();
            return new JObject { ["host_instance"] = session, ["kind"] = "solidworks", ["capabilities"] = new JArray(Methods),
                ["active_document"] = app.IActiveDoc2 == null ? null : InspectionRef(app.IActiveDoc2),
                ["documents"] = new JArray(docs.Select(d => new JObject { ["document"] = InspectionRef(d),
                    ["name"] = d.GetTitle(), ["path"] = d.GetPathName(), ["objects"] = new JArray(InspectionBodies(d).Select(b => new JObject {
                        ["native_ref"] = RequiredPersistent(d, b), ["label"] = b.Name, ["kind"] = "body" })) })) };
        }
        private (ModelDoc2 Model, Body2 Body, JObject Reference) InspectionBound(JObject p)
        {
            var docs = OpenInspectionDocuments();
            var reference = p["document"] as JObject ?? throw new CommandError("invalid_request", "缺少 document 引用");
            if (Protocol.Required(reference, "host_instance") != session)
                throw new CommandError("stale_session", "宿主实例已改变");
            var id = Protocol.Required(reference, "document_id");
            var model = docs.SingleOrDefault(d => inspectionDocuments[d] == id)
                ?? throw new CommandError("document_missing", "文档已关闭，请重新读取上下文");
            if (model.GetType() != (int)swDocumentTypes_e.swDocPART || model.IsOpenedViewOnly())
                throw new CommandError("unsupported_document", "需要已完整加载的零件文档");
            if (!JToken.DeepEquals(InspectionRef(model), reference))
                throw new CommandError("stale_document", "文档修订或配置已改变，请重新读取上下文");
            var bytes = Convert.FromBase64String(Protocol.Required(p, "object_ref"));
            var body = model.Extension.GetObjectByPersistReference3(bytes, out var error) as Body2;
            if (error != 0 || body == null || !InspectionBodies(model).Contains(body))
                throw new CommandError("entity_missing", "实体不属于当前零件修订");
            return (model, body, reference);
        }
        private static string RequiredPersistent(ModelDoc2 model, object entity) => Persistent(model, entity)
            ?? throw new CommandError("reference_unavailable", "宿主没有返回可定位的原生引用");
        private static double[] D(object values) => Items(values).Select(Convert.ToDouble).ToArray();
        private static double Dot(double[] a, double[] b) => a.Zip(b, (x, y) => x * y).Sum();
        private static double[] Sub(double[] a, double[] b) => a.Zip(b, (x, y) => x - y).ToArray();
        private static double[] Unit(double[] a)
        {
            var length = Math.Sqrt(Dot(a, a));
            if (a.Length != 3 || length == 0 || a.Any(v => double.IsNaN(v) || double.IsInfinity(v)))
                throw new CommandError("invalid_direction", "方向必须为有限的非零三维向量");
            return a.Select(v => v / length).ToArray();
        }
        private static double[] LinePoint(double[] point, double[] axis) => Sub(point, axis.Select(v => v * Dot(point, axis)).ToArray());
        private static double[] Cross(double[] a, double[] b) => new[] { a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0] };

        private JArray InspectionFeatures(ModelDoc2 model, Body2 body)
        {
            var result = new JArray();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            void Visit(Feature f, string parent)
            {
                if (f == null) return;
                var reference = RequiredPersistent(model, f);
                if (!seen.Add(reference)) return;
                var parameters = new JArray();
                var display = (DisplayDimension)f.GetFirstDisplayDimension();
                while (display != null)
                {
                    var dim = (Dimension)display.GetDimension2(0);
                    if (dim != null)
                    {
                        var type = (swDimensionType_e)display.Type2;
                        var unit = type == swDimensionType_e.swAngularDimension ? "rad" :
                            type == swDimensionType_e.swLinearDimension || type == swDimensionType_e.swDiameterDimension || type == swDimensionType_e.swRadialDimension ? "m" : "system";
                        parameters.Add(new JObject { ["name"] = dim.FullName, ["value"] = Value(dim, Configuration(model)),
                            ["unit"] = unit, ["read_only"] = dim.ReadOnly, ["driven_state"] = dim.DrivenState });
                    }
                    display = (DisplayDimension)f.GetNextDisplayDimension(display);
                }
                var code = f.GetErrorCode2(out var warning);
                var row = new JObject { ["native_ref"] = reference, ["parent"] = parent, ["label"] = f.Name,
                    ["type"] = f.GetTypeName2(), ["parameter_scope"] = "display_dimensions", ["parameters"] = parameters, ["error_code"] = code, ["warning"] = code != 0 && warning,
                    ["state"] = new JArray(code != 0 && !warning ? new[] { "Error" } : new string[0]),
                    ["dependencies"] = new JArray(Items(f.GetParents()).Cast<Feature>().Select(x => RequiredPersistent(model, x))) };
                if (f.GetSpecificFeature2() is Sketch sketch)
                {
                    var status = (swConstrainedStatus_e)sketch.GetConstrainedStatus();
                    var relations = new JArray(Items(sketch.RelationManager.GetRelations((int)swSketchRelationFilterType_e.swAll))
                        .Where(r => r != null).Cast<SketchRelation>().Select((r, index) => new JObject {
                            ["index"] = index, ["type"] = ((swConstraintType_e)r.GetRelationType()).ToString() }));
                    row["sketch"] = new JObject { ["status"] = status == swConstrainedStatus_e.swFullyConstrained ? "fully_constrained" :
                            status == swConstrainedStatus_e.swUnderConstrained ? "under_constrained" :
                            status == swConstrainedStatus_e.swOverConstrained ? "conflicting" : "unknown", ["native_status"] = (int)status,
                        ["fully_constrained"] = status == swConstrainedStatus_e.swFullyConstrained,
                        ["degrees_of_freedom"] = null, ["constraints"] = relations,
                        ["geometry_count"] = Items(sketch.GetSketchSegments()).Count() };
                }
                result.Add(row);
                var child = (Feature)f.GetFirstSubFeature();
                while (child != null) { Visit(child, reference); child = (Feature)child.GetNextSubFeature(); }
                foreach (Feature dependency in Items(f.GetParents())) Visit(dependency, null);
            }
            foreach (Feature feature in Items(body.GetFeatures())) Visit(feature, null);
            return result;
        }
        private static JObject InspectionEdge(Edge edge, string reference)
        {
            var curve = (Curve)edge.GetCurve();
            var parameters = edge.GetCurveParams3();
            var start = D(parameters.StartPoint); var end = D(parameters.EndPoint);
            var row = new JObject { ["native_ref"] = reference, ["kind"] = "other",
                ["start"] = new JArray(start), ["end"] = new JArray(end),
                ["length"] = curve.GetLength3(parameters.UMinValue, parameters.UMaxValue),
                ["sampling"] = "parameter_uniform_16_segments_display_only",
                ["samples"] = new JArray(Enumerable.Range(0, 17).Select(k => new JArray(D(curve.Evaluate2(
                    parameters.UMinValue+(parameters.UMaxValue-parameters.UMinValue)*k/16, 0)).Take(3)))) };
            if (curve.IsCircle())
            {
                var values = D(curve.CircleParams);
                row["kind"] = "circle"; row["point"] = new JArray(values.Take(3));
                row["direction"] = new JArray(Unit(values.Skip(3).Take(3).ToArray())); row["radius"] = values[6];
                row["angular_span"] = (double)row["length"]/values[6];
            }
            else if (curve.IsLine())
            {
                row["kind"] = "line"; row["point"] = new JArray(start); row["direction"] = new JArray(Unit(Sub(end, start)));
            }
            return row;
        }
        private JObject InspectModel(JObject p)
        {
            var (model, body, reference) = InspectionBound(p);
            var features = InspectionFeatures(model, body);
            var issues = new JArray(features.OfType<JObject>().Where(f => f["state"].Any()).Select(f => new JObject {
                ["native_ref"] = f["native_ref"], ["state"] = f["state"].DeepClone() }));
            if (model.Extension.NeedsRebuild2 != 0) issues.Add(new JObject { ["state"] = new JArray("needs_rebuild") });
            var faces = new JArray();
            foreach (Face2 face in Items(body.GetFaces()))
            {
                var surface = (Surface)face.GetSurface();
                var row = new JObject { ["native_ref"] = RequiredPersistent(model, face), ["kind"] = "other", ["area"] = face.GetArea() };
                if (surface.IsCylinder())
                {
                    var values = D(surface.CylinderParams); var axis = Unit(values.Skip(3).Take(3).ToArray()); var point = values.Take(3).ToArray();
                    var uv = D(face.GetUVBounds());
                    var xyz = D(surface.Evaluate((uv[0]+uv[1])/2, (uv[2]+uv[3])/2, 0, 0)).Take(3).ToArray();
                    var normal = D(surface.EvaluateAtPoint(xyz[0], xyz[1], xyz[2])).Take(3).ToArray();
                    if (face.FaceInSurfaceSense()) normal = normal.Select(v => -v).ToArray();
                    row["kind"] = "cylinder"; row["radius"] = values[6]; row["direction"] = new JArray(axis);
                    row["point"] = new JArray(LinePoint(point, axis)); row["inward"] = Dot(normal, LinePoint(Sub(xyz, point), axis)) < 0;
                    row["angular_span"] = Math.Abs(uv[1]-uv[0]);
                }
                else if (surface.IsPlane())
                {
                    var values = D(surface.PlaneParams);
                    var axis = Unit(values.Take(3).ToArray()); var offset = Dot(values.Skip(3).Take(3).ToArray(), axis);
                    row["kind"] = "plane"; row["direction"] = new JArray(axis);
                    row["point"] = new JArray(axis.Select(x => x * offset));
                }
                faces.Add(row);
            }
            var edges = new JArray(Items(body.GetEdges()).Cast<Edge>().Select(e => InspectionEdge(e, RequiredPersistent(model, e))));
            var result = new JObject { ["document"] = reference.DeepClone(), ["object_ref"] = p["object_ref"],
                ["coordinate_system"] = "document", ["length_unit"] = "m", ["angle_unit"] = "rad",
                ["state"] = issues.Count == 0 ? "ready" : "needs_rebuild", ["issues"] = issues,
                ["features"] = features, ["faces"] = faces, ["edges"] = edges };
            InspectionBound(p);
            return result;
        }
        private JObject InspectSection(JObject p)
        {
            var (model, body, reference) = InspectionBound(p);
            var plane = p["plane"] as JObject ?? throw new CommandError("invalid_request", "缺少截面平面");
            var origin = plane["origin"]?.ToObject<double[]>();
            if (origin == null || origin.Length != 3 || origin.Any(x => double.IsNaN(x) || double.IsInfinity(x)))
                throw new CommandError("invalid_request", "截面原点需要三个有限数值");
            var normal = Unit(plane["normal"]?.ToObject<double[]>() ?? new double[0]);
            var result = new JObject { ["document"] = reference.DeepClone(), ["object_ref"] = p["object_ref"],
                ["coordinate_system"] = "document", ["length_unit"] = "m", ["area_unit"] = "m^2",
                ["plane"] = new JObject { ["origin"] = new JArray(origin), ["normal"] = new JArray(normal) } };
            if (model.Extension.NeedsRebuild2 != 0 || InspectionFeatures(model, body).OfType<JObject>().Any(f => f["state"].Any()))
            { result["status"] = "unknown"; result["reason"] = "model_not_ready"; return result; }
            var u = Unit(Cross(normal, Math.Abs(normal[0]) < .9 ? new[] { 1.0, 0, 0 } : new[] { 0.0, 1, 0 }));
            var v = Cross(normal, u);
            // 包围盒仅用于让临时切割平面覆盖模型；量测不采用近似包围盒尺寸。
            var box = D(body.GetBodyBox());
            var size = Math.Sqrt(Dot(Sub(box.Take(3).ToArray(), origin), Sub(box.Take(3).ToArray(), origin))) +
                       Math.Sqrt(Dot(Sub(box.Skip(3).Take(3).ToArray(), origin), Sub(box.Skip(3).Take(3).ToArray(), origin))) + .001;
            var corners = new[] { new[] { -1, -1 }, new[] { 1, -1 }, new[] { 1, 1 }, new[] { -1, 1 } }
                .Select(sign => Enumerable.Range(0, 3).Select(k => origin[k]+size*(sign[0]*u[k]+sign[1]*v[k])).ToArray()).ToArray();
            var modeler = (Modeler)app.GetModeler();
            var surface = (Surface)modeler.CreatePlanarSurface2(origin, normal, u);
            var curves = new object[4];
            for (var k = 0; k < 4; k++)
            {
                var a = corners[k]; var b = corners[(k+1)%4];
                var line = (Curve)modeler.CreateLine(a, Sub(b, a));
                curves[k] = line.CreateTrimmedCurve2(a[0], a[1], a[2], b[0], b[1], b[2]);
            }
            var sheet = (Body2)surface.CreateTrimmedSheet5(curves, true, 1e-8);
            if (sheet == null) throw new CommandError("section_failed", "临时截面平面生成失败");
            // API 布尔操作会消费临时几何；绝不传文档中的原 Body。
            var copy = (Body2)body.Copy();
            var cuts = Items(sheet.Operations2((int)swBodyOperationType_e.SWBODYINTERSECT, copy, out var error)).Cast<Body2>().ToArray();
            if (error != 0 && error != (int)swBodyOperationError_e.swBodyOperationNoIntersect &&
                error != (int)swBodyOperationError_e.swBodyOperationDisjointBodies && error != (int)swBodyOperationError_e.swBodyOperationEmptyBody)
                throw new CommandError("section_failed", "原生截面计算失败，错误码 " + error);
            var cutEdges = cuts.SelectMany(b => Items(b.GetEdges()).Cast<Edge>()).ToArray();
            result["status"] = "ok";
            result["area"] = cuts.SelectMany(b => Items(b.GetFaces()).Cast<Face2>()).Sum(f => f.GetArea());
            result["edges"] = new JArray(cutEdges.Select((edge, index) => InspectionEdge(edge, "section.Edge"+(index+1))));
            InspectionBound(p);
            return result;
        }
    }
}
