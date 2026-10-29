using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using AcApplication = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Gongke.AutoCAD;

internal sealed class HostCommands(string session) : IDisposable
{
    private readonly Dictionary<Document, DocumentState> documents = new();
    public object Execute(Request request)
    {
        ObserveDocuments();
        var p = request.Params;
        return request.Method switch
        {
            "host.describe" => new {
                host = "autocad", instance_id = session, protocol_version = 1,
                version = AcApplication.Version.ToString(), runtime = RuntimeInformation.FrameworkDescription,
                pid = Environment.ProcessId, validation_level = "sdk_compiled_host_unverified",
                capabilities = new[] { "documents.list", "document.snapshot", "document.select", "drawing.edit_text",
                    "drawing.move_dimension_text", "drawing.import_dxf", "document.save_copy", "document.open", "operation.status", "operation.cancel" },
                entity_types = new[] { "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT", "DIMENSION" },
                limitations = new[] { "No nested block or xref editing", "Dimension measurements and text overrides are read-only", "No overwrite saves" }
            },
            "documents.list" => new { documents = documents.Select(x => Info(x.Key, x.Value)).ToArray() },
            "document.snapshot" => Snapshot(p),
            "document.select" => Select(p),
            "drawing.edit_text" => EditText(p),
            "drawing.move_dimension_text" => MoveDimension(p),
            "drawing.import_dxf" => ImportDxf(p),
            "document.save_copy" => SaveCopy(p),
            "document.open" => Open(p),
            _ => throw new BridgeException("unsupported_method", $"Unsupported method: {request.Method}")
        };
    }
    private void ObserveDocuments()
    {
        var live = AcApplication.DocumentManager.Cast<Document>().ToHashSet();
        foreach (var closed in documents.Keys.Where(x => !live.Contains(x)).ToArray())
        { documents[closed].Dispose(); documents.Remove(closed); }
        foreach (var doc in live)
            if (!documents.ContainsKey(doc)) documents.Add(doc, new DocumentState(doc, session));
    }
    private static object Info(Document doc, DocumentState state) => new {
        document_id = state.Id, revision = state.Revision, path = doc.Name,
        fingerprint = doc.Database.FingerprintGuid.ToString(), active = doc == AcApplication.DocumentManager.MdiActiveDocument,
        dirty = doc == AcApplication.DocumentManager.MdiActiveDocument ? Convert.ToInt32(AcApplication.GetSystemVariable("DBMOD")) != 0 : (bool?)null,
        read_only = doc.IsReadOnly, units = doc.Database.Insunits.ToString()
    };
    private (Document Doc, DocumentState State) Resolve(JsonElement p, bool verifyRevision = true, bool active = false)
    {
        var id = p.NonEmpty("document_id");
        var pair = documents.SingleOrDefault(x => x.Value.Id == id);
        if (pair.Key is null) throw new BridgeException("document_missing", "Document session was closed or replaced; refresh documents.");
        if (verifyRevision && pair.Value.Revision != p.Integer("expected_revision"))
            throw new BridgeException("stale_snapshot", "Drawing changed after this snapshot; refresh before editing.");
        if (active && pair.Key != AcApplication.DocumentManager.MdiActiveDocument)
            throw new BridgeException("document_not_active", "The selected drawing is not active; reconnect to the active drawing.");
        return (pair.Key, pair.Value);
    }
    private object Snapshot(JsonElement p)
    {
        var (doc, state) = Resolve(p, false);
        var offset = p.TryGetProperty("offset", out var off) ? off.GetInt32() : 0;
        var limit = p.TryGetProperty("limit", out var lim) ? lim.GetInt32() : 2000;
        if (offset < 0 || limit is < 1 or > 5000) throw new BridgeException("invalid_parameter", "offset >= 0; limit must be 1..5000.");
        if (offset > 0 && state.Revision != p.Integer("expected_revision"))
            throw new BridgeException("stale_snapshot", "Drawing changed while reading pages; restart the snapshot.");
        using var documentLock = doc.LockDocument();
        using var tx = doc.Database.TransactionManager.StartOpenCloseTransaction();
        var rows = new List<object>();
        var counts = new Dictionary<string, int>();
        int index = 0;
        var blocks = (BlockTable)tx.GetObject(doc.Database.BlockTableId, OpenMode.ForRead);
        foreach (ObjectId blockId in blocks)
        {
            var block = (BlockTableRecord)tx.GetObject(blockId, OpenMode.ForRead);
            if (!block.IsLayout) continue;
            var layout = (Layout)tx.GetObject(block.LayoutId, OpenMode.ForRead);
            foreach (ObjectId entityId in block)
            {
                if (entityId.IsErased || tx.GetObject(entityId, OpenMode.ForRead) is not Entity entity) continue;
                var type = entity.GetRXClass().DxfName;
                counts[type] = counts.GetValueOrDefault(type) + 1;
                if (index++ < offset || rows.Count >= limit) continue;
                rows.Add(EntitySnapshot.Read(entity, tx, layout.LayoutName));
            }
        }
        return new { document = Info(doc, state), entities = rows, entity_counts = counts,
            offset, total_entities = index, next_offset = offset + rows.Count < index ? (int?)(offset + rows.Count) : null,
            nested_blocks_expanded = false, coordinate_system = "WCS", revision = state.Revision };
    }
    private ObjectId EntityId(Document doc, JsonElement p)
    {
        if (!long.TryParse(p.NonEmpty("handle"), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var value))
            throw new BridgeException("invalid_handle", "Entity handle must be hexadecimal.");
        if (!doc.Database.TryGetObjectId(new Handle(value), out var id) || id.IsNull || id.IsErased)
            throw new BridgeException("entity_missing", "The native entity no longer exists.");
        return id;
    }
    private static Entity Writable(Document doc, ObjectId id, Transaction tx)
    {
        if (doc.IsReadOnly) throw new BridgeException("read_only", "Drawing is read-only.");
        if (tx.GetObject(id, OpenMode.ForRead) is not Entity entity) throw new BridgeException("unsupported_entity", "Target is not an entity.");
        var owner = tx.GetObject(entity.OwnerId, OpenMode.ForRead) as BlockTableRecord;
        if (owner is null || !owner.IsLayout || owner.IsFromExternalReference)
            throw new BridgeException("unsupported_entity", "Only direct model/paper space entities are editable.");
        var layer = (LayerTableRecord)tx.GetObject(entity.LayerId, OpenMode.ForRead);
        if (layer.IsLocked) throw new BridgeException("locked_layer", "The entity's layer is locked.");
        entity.UpgradeOpen();
        return entity;
    }
    private object Select(JsonElement p)
    {
        var (doc, state) = Resolve(p, true, true);
        using var documentLock = doc.LockDocument();
        var id = EntityId(doc, p);
        using var tx = doc.Database.TransactionManager.StartOpenCloseTransaction();
        if (tx.GetObject(id, OpenMode.ForRead) is not Entity entity) throw new BridgeException("unsupported_entity", "Only drawing entities can be selected.");
        var owner = tx.GetObject(entity.OwnerId, OpenMode.ForRead) as BlockTableRecord;
        if (owner is null || !owner.IsLayout) throw new BridgeException("unsupported_entity", "Nested block entities cannot be selected directly.");
        var layout = (Layout)tx.GetObject(owner.LayoutId, OpenMode.ForRead);
        LayoutManager.Current.CurrentLayout = layout.LayoutName;
        doc.Editor.SetImpliedSelection([id]);
        return new { document_id = state.Id, revision = state.Revision, handle = id.Handle.ToString(), selected = true };
    }
    private object EditText(JsonElement p)
    {
        var (doc, state) = Resolve(p, true, true);
        var text = p.Text("text");
        if (text.Length > 10000 || text.IndexOf('\0') >= 0 || text.Contains("%<"))
            throw new BridgeException("invalid_parameter", "Text must contain at most 10000 characters and no NUL or field expressions.");
        using var documentLock = doc.LockDocument();
        var id = EntityId(doc, p);
        using (var tx = doc.Database.TransactionManager.StartTransaction())
        {
            var entity = Writable(doc, id, tx);
            switch (entity)
            {
                case DBText single:
                    if (text.Contains('\r') || text.Contains('\n')) throw new BridgeException("invalid_parameter", "TEXT is single-line; use MTEXT for paragraphs.");
                    if (single.HasFields) throw new BridgeException("field_controlled", "Field-driven text is not editable.");
                    single.TextString = text;
                    single.AdjustAlignment(doc.Database);
                    break;
                case MText multi:
                    if (multi.HasFields) throw new BridgeException("field_controlled", "Field-driven text is not editable.");
                    // Input is plain text. Escape MTEXT control syntax rather than executing formatting/fields.
                    multi.Contents = text.Replace("\\", "\\\\").Replace("{", "\\{").Replace("}", "\\}").Replace("\r\n", "\n").Replace("\n", "\\P");
                    break;
                default: throw new BridgeException("unsupported_entity", "Only TEXT/MTEXT may be edited; dimension text overrides are not writable.");
            }
            tx.Commit();
        }
        doc.Editor.Regen();
        return Readback(doc, state, id, p.NonEmpty("operation_id"));
    }
    private object MoveDimension(JsonElement p)
    {
        var (doc, state) = Resolve(p, true, true);
        var coordinates = p.Point("position");
        using var documentLock = doc.LockDocument();
        var id = EntityId(doc, p);
        using (var tx = doc.Database.TransactionManager.StartTransaction())
        {
            if (Writable(doc, id, tx) is not Dimension dimension)
                throw new BridgeException("unsupported_entity", "Target must be a native DIMENSION, not LINE/TEXT export fragments.");
            var beforeMeasurement = dimension.Measurement;
            var beforeOverride = dimension.DimensionText;
            dimension.Dimtmove = 2;
            dimension.TextPosition = new Point3d(coordinates[0], coordinates[1], coordinates[2]);
            dimension.RecomputeDimensionBlock(true);
            if (dimension.Measurement != beforeMeasurement || dimension.DimensionText != beforeOverride)
                throw new BridgeException("dimension_changed", "Moving text unexpectedly changed the measurement or override; transaction rolled back.");
            tx.Commit();
        }
        doc.Editor.Regen();
        return Readback(doc, state, id, p.NonEmpty("operation_id"));
    }
    private static object Readback(Document doc, DocumentState state, ObjectId id, string operationId)
    {
        using var tx = doc.Database.TransactionManager.StartOpenCloseTransaction();
        var entity = (Entity)tx.GetObject(id, OpenMode.ForRead);
        var owner = (BlockTableRecord)tx.GetObject(entity.OwnerId, OpenMode.ForRead);
        var layout = (Layout)tx.GetObject(owner.LayoutId, OpenMode.ForRead);
        return new { operation_id = operationId, outcome = "committed", document = Info(doc, state), entity = EntitySnapshot.Read(entity, tx, layout.LayoutName) };
    }
    private object ImportDxf(JsonElement p)
    {
        var source = FilePolicy.Existing(p.NonEmpty("source_path"), ".dxf");
        var target = FilePolicy.NewDwg(p.NonEmpty("target_path"));
        var staging = FilePolicy.Staging(target);
        var log = Path.ChangeExtension(staging, ".log");
        try
        {
            // Autodesk explicitly requires buildDefaultDrawing=false for DxfIn.
            using (var database = new Database(false, true))
            {
                database.DxfIn(source, log);
                database.SaveAs(staging, DwgVersion.Current);
            }
            using (var verify = new Database(false, true))
            {
                verify.ReadDwgFile(staging, FileOpenMode.OpenForReadAndAllShare, false, "");
                verify.CloseInput(true);
            }
            FilePolicy.Publish(staging, target);
            return new { operation_id = p.NonEmpty("operation_id"), outcome = "committed", source_path = source, path = target,
                disk_reopen_verified = true, original_preserved = true, import_log = File.Exists(log) ? log : null };
        }
        finally { if (File.Exists(staging)) File.Delete(staging); }
    }
    private object SaveCopy(JsonElement p)
    {
        var (doc, state) = Resolve(p);
        var target = FilePolicy.NewDwg(p.NonEmpty("target_path"));
        var staging = FilePolicy.Staging(target);
        using var documentLock = doc.LockDocument();
        try
        {
            // Wblock() creates a complete in-memory database copy, preserving unsaved edits.
            using (var copy = doc.Database.Wblock()) copy.SaveAs(staging, DwgVersion.Current);
            using (var verify = new Database(false, true))
            {
                verify.ReadDwgFile(staging, FileOpenMode.OpenForReadAndAllShare, false, "");
                verify.CloseInput(true);
            }
            FilePolicy.Publish(staging, target);
            return new { operation_id = p.NonEmpty("operation_id"), outcome = "committed", document_id = state.Id,
                revision = state.Revision, path = target, disk_reopen_verified = true, original_preserved = true,
                source_document_remains_open = true };
        }
        finally { if (File.Exists(staging)) File.Delete(staging); }
    }
    private object Open(JsonElement p)
    {
        var path = FilePolicy.Existing(p.NonEmpty("path"), ".dwg");
        var existing = documents.Keys.FirstOrDefault(d => string.Equals(d.Name, path, StringComparison.OrdinalIgnoreCase));
        var doc = existing ?? AcApplication.DocumentManager.Open(path, false);
        AcApplication.DocumentManager.MdiActiveDocument = doc;
        ObserveDocuments();
        return Info(doc, documents[doc]);
    }
    public void Dispose() { foreach (var state in documents.Values) state.Dispose(); documents.Clear(); }
    private sealed class DocumentState : IDisposable
    {
        private readonly Database database;
        internal string Id { get; }
        internal long Revision { get; private set; }
        internal DocumentState(Document doc, string session)
        {
            Id = $"{session}:{Guid.NewGuid():N}";
            database = doc.Database;
            database.ObjectModified += OnChanged;
            database.ObjectAppended += OnChanged;
            database.ObjectErased += OnErased;
        }
        private void OnChanged(object sender, ObjectEventArgs e) => Revision++;
        private void OnErased(object sender, ObjectErasedEventArgs e) => Revision++;
        public void Dispose()
        {
            database.ObjectModified -= OnChanged;
            database.ObjectAppended -= OnChanged;
            database.ObjectErased -= OnErased;
        }
    }
}
