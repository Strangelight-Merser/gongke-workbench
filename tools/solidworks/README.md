# SOLIDWORKS 只读采集原型

从当前运行的 SOLIDWORKS 读取活动零件、尺寸原始标识和已打开工程图的视图引用，导出一个新 JSON 文件。宏不修改尺寸、显示设置或配置，不重建、不保存 CAD 文件，也不启动另一份 SOLIDWORKS。

目前只有源码核对和合成 JSON 测试，**尚未在 Windows / SOLIDWORKS 编译或运行**。这不是现有 FreeCAD 原生编辑能力的 SOLIDWORKS 版本。

## 运行

1. 在 Windows 的 SOLIDWORKS 中打开目标 `.SLDPRT`，使其成为活动文档并停留在需要读取的配置。需要检查关联的 `.SLDDRW` 也应已经打开；宏不会搜索磁盘或打开其他文件。
2. 在 SOLIDWORKS 的“工具 → 宏 → 新建”中创建宏。在 VBA 编辑器导入本目录的 `CollectCurrentPart.bas` 模块，运行该模块的 `main`。如果改用粘贴源码，跳过第一行 `Attribute VB_Name`，那是模块导入信息。宏使用 late binding 和 Windows 内置文件组件，不要求额外安装 Python COM 包或 SDK。
3. 输入一个**尚不存在**的 JSON 文件路径。文件已存在会报错并保留原文件。采集问题会保留在 JSON 的 `issues` 中；导出成功不等于所有字段都读到了。
4. 可在有 Python 3.10+ 的机器上检查文件，无需安装 SOLIDWORKS：

   ```sh
   python tools/solidworks/read_capture.py /path/to/capture.json
   ```

   命令只读取 JSON，显示文档、数量、问题及按完整模型路径和配置名匹配的已打开图纸视图。退出码 0 表示文件契约合格，允许 `partial` / `unsupported` / `error` 状态；请同时看输出的 `status`。格式错误退出码为 1。

## 采集内容与边界

- `document`：活动文档的真实路径、标题、类型和活动配置。只支持零件（类型 1）；装配体、图纸或没有活动文档会标记 `unsupported`。未保存零件没有路径，字段为 `null`，状态为 `partial`。
- `dimensions`：`IDimension.FullName`、来源特征名、当前配置的 `GetSystemValue3` 值、参数类型、`DrivenState` 和 `ReadOnly`。线性值以米、角度以弧度输出；整数参数的单位为 `integer`，不是长度。`DrivenState` 保留官方枚举整数。读取失败的字段为 `null`，该记录为 `partial`。`ReadOnly=false` 不能单独证明允许编辑；方程、设计表等驱动关系尚未检查。
- `open_drawings`：当前实例已打开图纸中各 sheet 的视图，保留真实 `GetReferencedModelName` 与 `ReferencedConfiguration`。不按同名文件猜测关联，也不把另一个配置算作当前配置。没打开的图纸、磁盘引用是否存在和工程图是否已更新均未验证。
- `status=collected`：本轮枚举的记录字段读取成功。**不保证全部尺寸都被枚举。** 官方特征尺寸接口要求尺寸已显示；宏不会为此改显示设置，所以始终输出 `enumeration_completeness=not_established`。零尺寸会标记 `partial`，不能据此判断模型没有尺寸。
- `engineering_semantics=unmapped`：尺寸名称与轴段、直径、圆角尚未建立明确映射。宏不猜测轴段，不推断材料、载荷或边界条件，不调用现有轴校核器，不把采集结果说成工程通过。
- `prototype_validation=unverified`：该版本采集器尚无 SOLIDWORKS 实机验收；这是版本验证状态，不替代单次采集的 `status`。

JSON 使用 ASCII 加 Unicode 转义，中文文件名、特征名和配置名可由标准 JSON 解析器恢复。运行说明只交付 `.bas` 源码，不声称已经生成或验证可执行 `.swp`。

下一次实机验证应直接比较已有零件的活动配置与尺寸、工程图视图的模型和配置引用，并确认采集前后 CAD 文件及未保存修改保持原样。在此之前不能声称支持原生写入、重建或撤销。

## 公开 API 依据

- [IFeature.GetNextDisplayDimension](https://help.solidworks.com/2024/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeature~GetNextDisplayDimension.html)：特征与子特征尺寸枚举及显示前提；[IDisplayDimension.GetDimension2](https://help.solidworks.com/2019/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.idisplaydimension~getdimension2.html)：倒角的两个尺寸与普通尺寸索引行为。
- [官方 GetSystemValue3 VBA 示例](https://help.solidworks.com/2012/english/api/sldworksapi/Change_Dimensions_of_Gear_Mate_Example_VB.htm)：当前配置与 Empty 参数；[参数类型枚举](https://help.solidworks.com/2024/English/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swDimensionParamType_e.html)：线性、角度和整数类型；[API 单位](https://help.solidworks.com/2024/english/api/sldworksapiprogguide/Overview/Units.htm)：系统单位。
- [ISldWorks.GetDocuments](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isldworks~getdocuments.html)、[IDrawingDoc.GetViews](https://help.solidworks.com/2016/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDrawingDoc~GetViews.html)：当前打开的文档及各 sheet 的视图数组，第一项为 sheet 本身。
