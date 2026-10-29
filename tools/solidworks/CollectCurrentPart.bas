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
    Dim revision As Variant, selected As String, before As String, after As String
    Set issues = New Collection
    Set dims = New Collection
    Set drawings = New Collection
    status = "error": document = "null": selected = "null"
    before = "[]": after = "[]": revision = Null
    On Error GoTo Failed
    ' 在 SOLIDWORKS 内运行，使用该实例；不创建或猜测另一个 COM 实例。
    Set sw = Application.SldWorks
    revision = ReadText(sw, "RevisionNumber", VbMethod, "host.revision_number")
    before = StateJson(sw)
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
                selected = SelectedTargetJson(model)
                If dims.Count = 0 Then AddIssue "dimensions", "none_enumerated_not_proof_of_no_dimensions"
            Else
                AddIssue "active_document", "only_part_document_supported"
            End If
        End If
    End If
    ReadOpenDrawings sw, drawings
    after = StateJson(sw)
    If before <> after Then AddIssue "state", "observed_state_changed"
    If status = "collected" And issues.Count > 0 Then status = "partial"
    GoTo Finish
Failed:
    AddIssue "capture", Err.Description
    status = "error"
Finish:
    Capture = "{""schema_version"":2,""capture_kind"":""solidworks_readonly_inventory""," & _
              """prototype_validation"":""unverified"",""status"":" & J(status) & _
              ",""host"":{""revision_number"":" & J(revision) & ",""platform"":""Windows""}" & _
              ",""captured_at_local"":" & J(Format$(Now, "yyyy-mm-dd") & "T" & Format$(Now, "hh:nn:ss")) & _
              ",""document"":" & document & ",""enumeration_completeness"":""not_established""," & _
              """engineering_semantics"":""unmapped"",""dimensions"":" & JsonArray(dims) & _
              ",""selected_target"":" & selected & ",""state_before"":" & before & ",""state_after"":" & after & _
              ",""state_preservation"":""not_established"",""open_drawings"":" & JsonArray(drawings) & _
              ",""issues"":" & JsonArray(issues) & "}"
End Function

Private Function StateJson(ByVal sw As Object) As String
    Dim docs As Variant, model As Object, config As Object, selection As Object
    Dim rows As Collection, index As Long, kind As Variant, configuration As Variant, count As Variant
    Set rows = New Collection
    On Error GoTo Failed
    docs = sw.GetDocuments
    If IsEmpty(docs) Then GoTo Finish
    For index = LBound(docs) To UBound(docs)
        Set model = docs(index)
        kind = ReadScalar(model, "GetType", VbMethod, "state.type")
        configuration = Null
        If Not IsNull(kind) Then
            If kind = 1 Then
                Set config = model.ConfigurationManager.ActiveConfiguration
                configuration = ReadText(config, "Name", VbGet, "state.configuration")
            End If
        End If
        Set selection = model.SelectionManager
        count = selection.GetSelectedObjectCount2(-1)
        rows.Add "{""path"":" & J(ReadText(model, "GetPathName", VbMethod, "state.path")) & _
                 ",""title"":" & J(ReadText(model, "GetTitle", VbMethod, "state.title")) & _
                 ",""type"":" & J(kind) & ",""configuration"":" & J(configuration) & _
                 ",""save_flag"":" & J(ReadScalar(model, "GetSaveFlag", VbMethod, "state.save_flag")) & _
                 ",""selection_count"":" & J(count) & "}"
    Next index
    GoTo Finish
Failed:
    AddIssue "state.observation", Err.Description
Finish:
    ' 保存标志和选择数相同不能证明内存内容完全不变，必须保留人工对照。
    StateJson = JsonArray(rows)
End Function

Private Function SelectedTargetJson(ByVal model As Object) As String
    Dim selection As Object, display As Object, dimension As Object
    Dim count As Long, kind As Long, displayType As Variant, name As Variant, parameterType As Variant, unit As Variant
    SelectedTargetJson = "null"
    On Error GoTo Failed
    Set selection = model.SelectionManager
    count = selection.GetSelectedObjectCount2(-1)
    If count <> 1 Then
        AddIssue "selected_target", "select_exactly_one_dimension": Exit Function
    End If
    kind = selection.GetSelectedObjectType3(1, -1)
    If kind <> 14 Then
        AddIssue "selected_target", "selection_is_not_dimension": Exit Function
    End If
    Set display = selection.GetSelectedObject6(1, -1)
    displayType = ReadScalar(display, "Type2", VbGet, "selected_target.display_type")
    If IsNull(displayType) Then Exit Function
    If displayType = 10 Then
        AddIssue "selected_target", "chamfer_has_two_parameters_not_a_single_target": Exit Function
    End If
    Set dimension = DimensionAt(display, 0)
    If dimension Is Nothing Then Exit Function
    name = ReadText(dimension, "FullName", VbGet, "selected_target.full_name")
    parameterType = ReadScalar(dimension, "GetType", VbMethod, "selected_target.parameter_type")
    unit = Null
    If Not IsNull(parameterType) Then
        Select Case parameterType
            Case 0: unit = "m"
            Case 1: unit = "rad"
            Case 2: unit = "integer"
            Case Else: AddIssue "selected_target.unit", "unknown_parameter_type"
        End Select
    End If
    SelectedTargetJson = "{""full_name"":" & J(name) & ",""value_si"":" & J(DimensionValue(dimension)) & _
                         ",""parameter_type"":" & J(parameterType) & ",""unit"":" & J(unit) & _
                         ",""display_type"":" & J(displayType) & ",""selection_type"":14}"
    Exit Function
Failed:
    AddIssue "selected_target", Err.Description
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
    Dim displays As String, issueCount As Long
    issueCount = issues.Count
    name = ReadText(view, "GetName2", VbMethod, "view.name")
    model = ReadText(view, "GetReferencedModelName", VbMethod, "view.referenced_model")
    config = ReadText(view, "ReferencedConfiguration", VbGet, "view.referenced_configuration")
    displays = DisplayDimensionsJson(view)
    status = "read"
    If IsNull(sheetName) Or IsNull(name) Or IsNull(model) Or IsNull(config) Then status = "partial"
    If issues.Count > issueCount Then status = "partial"
    ViewJson = "{""sheet_name"":" & J(sheetName) & ",""view_name"":" & J(name) & _
               ",""referenced_model"":" & J(model) & ",""referenced_configuration"":" & J(config) & _
               ",""status"":" & J(status) & ",""display_dimensions"":" & displays & _
               ",""annotation_coverage"":""not_established"",""view_update_status"":""not_checked""}"
End Function

Private Function DisplayDimensionsJson(ByVal view As Object) As String
    Dim rows As Collection, display As Object
    Set rows = New Collection
    On Error GoTo Failed
    Set display = view.GetFirstDisplayDimension5
    Do While Not display Is Nothing
        rows.Add DisplayDimensionJson(display)
        Set display = display.GetNext5
    Loop
    GoTo Finish
Failed:
    AddIssue "view.display_dimensions", Err.Description
Finish:
    DisplayDimensionsJson = JsonArray(rows)
End Function

Private Function DisplayDimensionJson(ByVal display As Object) As String
    Dim annotation As Object, dimension As Object, names As Collection
    Dim name As Variant, fullName As Variant, dangling As Variant, overridden As Variant
    Dim overrideValue As Variant, displayType As Variant, status As String, lastIndex As Long, index As Long, issueCount As Long
    Set names = New Collection
    issueCount = issues.Count
    name = Null: dangling = Null: overrideValue = Null: status = "read"
    displayType = ReadScalar(display, "Type2", VbGet, "annotation.display_type")
    overridden = ReadScalar(display, "GetOverride", VbMethod, "annotation.override")
    If Not IsNull(overridden) Then
        If overridden Then overrideValue = ReadScalar(display, "GetOverrideValue", VbMethod, "annotation.override_value")
    End If
    On Error GoTo Failed
    Set annotation = display.GetAnnotation
    name = ReadText(annotation, "GetName", VbMethod, "annotation.name")
    dangling = ReadScalar(annotation, "IsDangling", VbMethod, "annotation.dangling")
    lastIndex = 0
    If Not IsNull(displayType) Then
        If displayType = 10 Then lastIndex = 1
    End If
    For index = 0 To lastIndex
        Set dimension = DimensionAt(display, index)
        If Not dimension Is Nothing Then
            fullName = ReadText(dimension, "FullName", VbGet, "annotation.dimension_full_name")
            If Not IsNull(fullName) Then names.Add J(fullName)
        End If
    Next index
    GoTo Finish
Failed:
    AddIssue "annotation", Err.Description
    status = "partial"
Finish:
    If issues.Count > issueCount Then status = "partial"
    If IsNull(name) Or IsNull(dangling) Or IsNull(overridden) Or IsNull(displayType) Or names.Count = 0 Then status = "partial"
    If Not IsNull(overridden) Then
        If overridden And IsNull(overrideValue) Then status = "partial"
    End If
    ' 数值覆盖保留 API 原始值；单位、整段文字覆盖与公差在此原型中尚未核对。
    DisplayDimensionJson = "{""annotation_name"":" & J(name) & ",""dimension_full_names"":" & JsonArray(names) & _
                           ",""display_type"":" & J(displayType) & ",""override"":" & J(overridden) & _
                           ",""override_value"":" & J(overrideValue) & ",""override_value_unit"":""not_established""," & _
                           """dangling"":" & J(dangling) & ",""text_override_status"":""not_checked""," & _
                           """status"":" & J(status) & "}"
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
