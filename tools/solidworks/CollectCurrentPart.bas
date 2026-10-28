Attribute VB_Name = "CollectCurrentPart"
Option Explicit

' 只读采集原型：尚未在 Windows / SOLIDWORKS 实机验证。
' 所有 SOLIDWORKS 对象均 late binding；不改尺寸、显示设置、配置或 CAD 文件。
Private issues As Collection

Public Sub main()
    Dim outputPath As String, payload As String
    Dim fs As Object, stream As Object
    On Error GoTo Failed
    outputPath = InputBox("New JSON output file (existing files are refused):", _
                         "GongKe read-only inventory", _
                         Environ$("TEMP") & "\gongke-solidworks-" & Format$(Now, "yyyymmdd-hhnnss") & ".json")
    If Len(outputPath) = 0 Then Exit Sub
    payload = Capture()
    Set fs = CreateObject("Scripting.FileSystemObject")
    ' overwrite=False：文件存在时失败，不覆盖。J() 将非 ASCII 字符编码为 JSON 转义。
    Set stream = fs.CreateTextFile(outputPath, False, False)
    stream.Write payload
    stream.Close
    MsgBox "Read-only inventory written to:" & vbCrLf & outputPath & vbCrLf & _
           "This is raw data, not a shaft validation or proof of complete dimension coverage."
    Exit Sub
Failed:
    MsgBox "Export failed: " & Err.Description, vbExclamation
End Sub

Private Function Capture() As String
    Dim sw As Object, model As Object, config As Object
    Dim dims As Collection, drawings As Collection
    Dim status As String, document As String, configuration As Variant
    Dim docType As Variant, docPath As Variant, title As Variant
    Set issues = New Collection
    Set dims = New Collection
    Set drawings = New Collection
    status = "error": document = "null"
    On Error GoTo Failed
    ' 在 SOLIDWORKS 内运行，使用该实例；不创建或猜测另一个 COM 实例。
    Set sw = Application.SldWorks
    Set model = sw.ActiveDoc
    If model Is Nothing Then
        status = "unsupported"
        AddIssue "active_document", "no_active_document"
    Else
        docType = ReadScalar(model, "GetType", VbMethod, "document.type")
        docPath = ReadText(model, "GetPathName", VbMethod, "document.path")
        title = ReadText(model, "GetTitle", VbMethod, "document.title")
        configuration = Null
        If Not IsNull(docType) Then
            If docType = 1 Then
                Set config = model.ConfigurationManager.ActiveConfiguration
                configuration = ReadText(config, "Name", VbGet, "document.configuration")
            End If
        End If
        document = "{""path"":" & J(docPath) & ",""title"":" & J(title) & _
                   ",""type"":" & J(docType) & ",""configuration"":" & J(configuration) & "}"
        status = "unsupported"
        If Not IsNull(docType) Then
            If docType = 1 Then
                status = "collected"
                ReadDimensions model, dims
                If dims.Count = 0 Then AddIssue "dimensions", "none_enumerated_not_proof_of_no_dimensions"
            Else
                AddIssue "active_document", "only_part_document_supported"
            End If
        End If
    End If
    ReadOpenDrawings sw, drawings
    If status = "collected" And issues.Count > 0 Then status = "partial"
    GoTo Finish
Failed:
    AddIssue "capture", Err.Description
    status = "error"
Finish:
    Capture = "{""schema_version"":1,""capture_kind"":""solidworks_readonly_inventory""," & _
              """prototype_validation"":""unverified"",""status"":" & J(status) & _
              ",""captured_at_local"":" & J(Format$(Now, "yyyy-mm-dd") & "T" & Format$(Now, "hh:nn:ss")) & _
              ",""document"":" & document & ",""enumeration_completeness"":""not_established""," & _
              """engineering_semantics"":""unmapped"",""dimensions"":" & JsonArray(dims) & _
              ",""open_drawings"":" & JsonArray(drawings) & ",""issues"":" & JsonArray(issues) & "}"
End Function

Private Sub ReadDimensions(ByVal model As Object, ByVal rows As Collection)
    Dim feature As Object, display As Object, dimObject As Object
    Dim seen As Object, fullName As Variant, featureName As Variant
    Dim index As Long
    On Error GoTo Failed
    Set seen = CreateObject("Scripting.Dictionary")
    Set feature = model.FirstFeature
    Do While Not feature Is Nothing
        featureName = ReadText(feature, "Name", VbGet, "feature.name")
        Set display = feature.GetFirstDisplayDimension
        Do While Not display Is Nothing
            ' 倒角可能有两条 Dimension；其他尺寸忽略 index，按 FullName 去重。
            For index = 0 To 1
                Set dimObject = DimensionAt(display, index)
                If Not dimObject Is Nothing Then
                    fullName = ReadText(dimObject, "FullName", VbGet, "dimension.full_name")
                    If IsNull(fullName) Then
                        rows.Add DimensionJson(dimObject, fullName, featureName)
                    ElseIf Not seen.Exists(CStr(fullName)) Then
                        seen.Add CStr(fullName), True
                        rows.Add DimensionJson(dimObject, fullName, featureName)
                    End If
                End If
            Next index
            Set display = feature.GetNextDisplayDimension(display)
        Loop
        Set feature = feature.GetNextFeature
    Loop
    Exit Sub
Failed:
    AddIssue "dimensions.enumeration", Err.Description
End Sub

Private Function DimensionAt(ByVal display As Object, ByVal index As Long) As Object
    On Error GoTo Failed
    Set DimensionAt = display.GetDimension2(index)
    If DimensionAt Is Nothing Then AddIssue "dimension", "GetDimension2_returned_null"
    Exit Function
Failed:
    AddIssue "dimension.GetDimension2", Err.Description
End Function

Private Function DimensionJson(ByVal dimension As Object, ByVal fullName As Variant, ByVal featureName As Variant) As String
    Dim value As Variant, kind As Variant, driven As Variant, readOnly As Variant
    Dim unit As Variant, status As String
    value = DimensionValue(dimension)
    kind = ReadScalar(dimension, "GetType", VbMethod, "dimension.parameter_type")
    driven = ReadScalar(dimension, "DrivenState", VbGet, "dimension.driven_state")
    readOnly = ReadScalar(dimension, "ReadOnly", VbGet, "dimension.read_only")
    unit = Null
    If Not IsNull(kind) Then
        Select Case kind
            Case 0: unit = "m"
            Case 1: unit = "rad"
            Case 2: unit = "integer"
            Case Else: AddIssue "dimension.unit", "unknown_parameter_type"
        End Select
    End If
    status = "read"
    If IsNull(fullName) Or IsNull(featureName) Or IsNull(value) Or IsNull(kind) Or IsNull(unit) Or IsNull(driven) Or IsNull(readOnly) Then status = "partial"
    DimensionJson = "{""full_name"":" & J(fullName) & ",""feature_name"":" & J(featureName) & _
                    ",""value_si"":" & J(value) & ",""parameter_type"":" & J(kind) & _
                    ",""unit"":" & J(unit) & ",""driven_state"":" & J(driven) & _
                    ",""read_only"":" & J(readOnly) & ",""status"":" & J(status) & "}"
End Function

Private Function DimensionValue(ByVal dimension As Object) As Variant
    Dim values As Variant, unused As Variant
    On Error GoTo Failed
    ' swThisConfiguration=1；第二参数仅指定配置时使用。返回一个元素的 Variant 数组。
    values = dimension.GetSystemValue3(1, unused)
    If Not IsArray(values) Then Err.Raise vbObjectError + 1, , "dimension_value_not_array"
    If UBound(values) <> LBound(values) Then Err.Raise vbObjectError + 2, , "dimension_value_not_single"
    DimensionValue = CDbl(values(LBound(values)))
    Exit Function
Failed:
    AddIssue "dimension.value_si", Err.Description
    DimensionValue = Null
End Function

Private Sub ReadOpenDrawings(ByVal sw As Object, ByVal rows As Collection)
    Dim documents As Variant, model As Object, index As Long, kind As Variant
    On Error GoTo Failed
    documents = sw.GetDocuments
    If IsEmpty(documents) Then Exit Sub
    If Not IsArray(documents) Then Err.Raise vbObjectError + 3, , "open_documents_not_array"
    For index = LBound(documents) To UBound(documents)
        Set model = documents(index)
        kind = ReadScalar(model, "GetType", VbMethod, "open_document.type")
        If Not IsNull(kind) Then
            If kind = 3 Then rows.Add DrawingJson(model)
        End If
    Next index
    Exit Sub
Failed:
    AddIssue "open_drawings.enumeration", Err.Description
End Sub

Private Function DrawingJson(ByVal drawing As Object) As String
    Dim sheets As Variant, views As Variant, view As Object
    Dim rows As Collection, sheetIndex As Long, viewIndex As Long, issueCount As Long
    Dim path As Variant, title As Variant, sheetName As Variant, status As String
    Set rows = New Collection
    issueCount = issues.Count
    status = "read"
    path = ReadText(drawing, "GetPathName", VbMethod, "drawing.path")
    title = ReadText(drawing, "GetTitle", VbMethod, "drawing.title")
    If IsNull(path) Or IsNull(title) Then status = "partial"
    On Error GoTo Failed
    sheets = drawing.GetViews
    If Not IsArray(sheets) Then Err.Raise vbObjectError + 4, , "drawing_views_not_array"
    For sheetIndex = LBound(sheets) To UBound(sheets)
        views = sheets(sheetIndex)
        Set view = views(LBound(views))
        sheetName = ReadText(view, "GetName2", VbMethod, "drawing.sheet")
        ' 每个数组的第一项是 sheet 本身，不是引用模型的视图。
        For viewIndex = LBound(views) + 1 To UBound(views)
            Set view = views(viewIndex)
            rows.Add ViewJson(view, sheetName)
        Next viewIndex
    Next sheetIndex
    GoTo Finish
Failed:
    AddIssue "drawing.views", Err.Description
    status = "partial"
Finish:
    If issues.Count > issueCount Then status = "partial"
    DrawingJson = "{""path"":" & J(path) & ",""title"":" & J(title) & _
                  ",""status"":" & J(status) & ",""views"":" & JsonArray(rows) & "}"
End Function

Private Function ViewJson(ByVal view As Object, ByVal sheetName As Variant) As String
    Dim name As Variant, model As Variant, config As Variant, status As String
    name = ReadText(view, "GetName2", VbMethod, "view.name")
    model = ReadText(view, "GetReferencedModelName", VbMethod, "view.referenced_model")
    config = ReadText(view, "ReferencedConfiguration", VbGet, "view.referenced_configuration")
    status = "read"
    If IsNull(sheetName) Or IsNull(name) Or IsNull(model) Or IsNull(config) Then status = "partial"
    ViewJson = "{""sheet_name"":" & J(sheetName) & ",""view_name"":" & J(name) & _
               ",""referenced_model"":" & J(model) & ",""referenced_configuration"":" & J(config) & _
               ",""status"":" & J(status) & "}"
End Function

Private Function ReadScalar(ByVal obj As Object, ByVal member As String, ByVal callType As VbCallType, ByVal field As String) As Variant
    On Error GoTo Failed
    ReadScalar = CallByName(obj, member, callType)
    If IsNull(ReadScalar) Or IsEmpty(ReadScalar) Then
        AddIssue field, "missing_value"
        ReadScalar = Null
    End If
    Exit Function
Failed:
    AddIssue field, Err.Description
    ReadScalar = Null
End Function

Private Function ReadText(ByVal obj As Object, ByVal member As String, ByVal callType As VbCallType, ByVal field As String) As Variant
    Dim value As Variant
    value = ReadScalar(obj, member, callType, field)
    If Not IsNull(value) Then
        If Len(CStr(value)) = 0 Then
            AddIssue field, "empty_value"
            value = Null
        End If
    End If
    ReadText = value
End Function

Private Sub AddIssue(ByVal field As String, ByVal detail As String)
    issues.Add J(field & ": " & detail)
End Sub

Private Function JsonArray(ByVal rows As Collection) As String
    Dim result As String, index As Long
    result = "["
    For index = 1 To rows.Count
        If index > 1 Then result = result & ","
        result = result & rows(index)
    Next index
    JsonArray = result & "]"
End Function

Private Function J(ByVal value As Variant) As String
    Dim result As String, ch As String, code As Long, index As Long
    If IsNull(value) Or IsEmpty(value) Then
        J = "null": Exit Function
    End If
    If VarType(value) = vbBoolean Then
        If value Then J = "true" Else J = "false"
        Exit Function
    End If
    If VarType(value) <> vbString Then
        J = Replace$(CStr(value), ",", "."): Exit Function
    End If
    result = Chr$(34)
    For index = 1 To Len(value)
        ch = Mid$(value, index, 1)
        code = AscW(ch) And &HFFFF&
        If code = 34 Or code = 92 Then
            result = result & Chr$(92) & ch
        ElseIf code < 32 Or code > 126 Then
            result = result & "\u" & Right$("0000" & Hex$(code), 4)
        Else
            result = result & ch
        End If
    Next index
    J = result & Chr$(34)
End Function
