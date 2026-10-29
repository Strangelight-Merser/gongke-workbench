using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Gongke.AutoCAD;

internal static class EntitySnapshot
{
    internal static object Read(Entity entity, Transaction tx, string layout)
    {
        var layer = (LayerTableRecord)tx.GetObject(entity.LayerId, OpenMode.ForRead);
        var data = new Dictionary<string, object?> {
            ["handle"] = entity.Handle.ToString(), ["type"] = entity.GetRXClass().DxfName,
            ["native_class"] = entity.GetType().Name, ["layout"] = layout, ["layer"] = entity.Layer,
            ["layer_locked"] = layer.IsLocked, ["visible"] = entity.Visible,
            ["color_index"] = entity.ColorIndex, ["linetype"] = entity.Linetype,
            ["editable"] = !layer.IsLocked && entity is DBText or MText or Dimension
        };
        switch (entity)
        {
            case Line line:
                data["geometry"] = new { start = Point(line.StartPoint), end = Point(line.EndPoint) };
                break;
            case Polyline polyline:
                data["geometry"] = new {
                    vertices = Enumerable.Range(0, polyline.NumberOfVertices).Select(i => new {
                        point = Point(polyline.GetPoint3dAt(i)), bulge = polyline.GetBulgeAt(i),
                        start_width = polyline.GetStartWidthAt(i), end_width = polyline.GetEndWidthAt(i)
                    }).ToArray(), closed = polyline.Closed, normal = Vector(polyline.Normal), elevation = polyline.Elevation
                };
                break;
            case Polyline2d polyline:
                data["geometry"] = new {
                    vertices = polyline.Cast<ObjectId>().Select(id => (Vertex2d)tx.GetObject(id, OpenMode.ForRead))
                        .Select(v => new { point = Point(polyline.VertexPosition(v)), bulge = v.Bulge, start_width = v.StartWidth, end_width = v.EndWidth }).ToArray(),
                    closed = polyline.Closed, normal = Vector(polyline.Normal), elevation = polyline.Elevation
                };
                break;
            case Polyline3d polyline:
                data["geometry"] = new {
                    vertices = polyline.Cast<ObjectId>().Select(id => (PolylineVertex3d)tx.GetObject(id, OpenMode.ForRead))
                        .Select(v => new { point = Point(v.Position), bulge = 0.0 }).ToArray(), closed = polyline.Closed
                };
                break;
            case Circle circle:
                data["geometry"] = new { center = Point(circle.Center), radius = circle.Radius, normal = Vector(circle.Normal) };
                break;
            case Arc arc:
                data["geometry"] = new { center = Point(arc.Center), radius = arc.Radius, start_angle = arc.StartAngle,
                    end_angle = arc.EndAngle, start = Point(arc.StartPoint), end = Point(arc.EndPoint), normal = Vector(arc.Normal) };
                break;
            case DBText text:
                data["text"] = text.TextString;
                data["geometry"] = new { position = Point(text.Position), alignment = Point(text.AlignmentPoint), height = text.Height,
                    rotation = text.Rotation, normal = Vector(text.Normal), width_factor = text.WidthFactor };
                data["field_controlled"] = text.HasFields;
                data["editable"] = !layer.IsLocked && !text.HasFields;
                break;
            case MText text:
                data["text"] = text.Text;
                data["contents"] = text.Contents;
                data["geometry"] = new { position = Point(text.Location), height = text.TextHeight, width = text.Width,
                    rotation = text.Rotation, normal = Vector(text.Normal), attachment = text.Attachment.ToString() };
                data["field_controlled"] = text.HasFields;
                data["editable"] = !layer.IsLocked && !text.HasFields;
                break;
            case Dimension dimension:
                data["measurement"] = dimension.Measurement;
                data["text_override"] = dimension.DimensionText;
                data["text_position"] = Point(dimension.TextPosition);
                data["dimension_scale"] = dimension.Dimscale;
                data["linear_factor"] = dimension.Dimlfac;
                data["text_movement"] = dimension.Dimtmove;
                data["normal"] = Vector(dimension.Normal);
                data["style"] = ((DimStyleTableRecord)tx.GetObject(dimension.DimensionStyle, OpenMode.ForRead)).Name;
                data["geometry"] = DimensionGeometry(dimension);
                data["editable_properties"] = new[] { "text_position" };
                break;
            default:
                data["editable"] = false;
                data["unsupported"] = true;
                break;
        }
        try { data["bounds"] = new { min = Point(entity.GeometricExtents.MinPoint), max = Point(entity.GeometricExtents.MaxPoint) }; }
        catch (Autodesk.AutoCAD.Runtime.Exception) { data["bounds"] = null; }
        return data;
    }
    private static object DimensionGeometry(Dimension dimension) => dimension switch
    {
        AlignedDimension d => new { first = Point(d.XLine1Point), second = Point(d.XLine2Point), line = Point(d.DimLinePoint) },
        RotatedDimension d => new { first = Point(d.XLine1Point), second = Point(d.XLine2Point), line = Point(d.DimLinePoint), rotation = d.Rotation },
        RadialDimension d => new { center = Point(d.Center), chord = Point(d.ChordPoint) },
        DiametricDimension d => new { chord = Point(d.ChordPoint), far_chord = Point(d.FarChordPoint) },
        LineAngularDimension2 d => new { first_start = Point(d.XLine1Start), first_end = Point(d.XLine1End),
            second_start = Point(d.XLine2Start), second_end = Point(d.XLine2End), arc = Point(d.ArcPoint) },
        Point3AngularDimension d => new { center = Point(d.CenterPoint), first = Point(d.XLine1Point), second = Point(d.XLine2Point), arc = Point(d.ArcPoint) },
        _ => new { supported_preview = false }
    };
    private static double[] Point(Point3d point) => [point.X, point.Y, point.Z];
    private static double[] Vector(Vector3d vector) => [vector.X, vector.Y, vector.Z];
}
