# SOLIDWORKS 借机只读验证包

在已经可以正常运行 SOLIDWORKS 的 Windows 电脑上采集一份现有零件和关联工程图。只需解压本包并导入 VBA 模块，**不需要安装 Git、Python、插件或 SDK**。JSON 带回开发机检查。

当前是 v2 源码探针，**尚未在 Windows / SOLIDWORKS 编译或运行**；没有可直接双击的已验证 `.swp`。首次借机的成果是实际编译与读取证据。没有修改、重建、撤销或图纸同步能力。

## 借机前准备

- 准备一套已获使用许可的 `.SLDPRT` 与关联 `.SLDDRW`，优先用课程轴的工作副本。保持图纸指向该副本；单独复制或同名文件不能证明引用正确。
- 使用电脑上现有的 SOLIDWORKS 年份/SP，无需为探针升级。先确认它能打开这套原生工程。
- 本包不含原生模型与 SOLIDWORKS 安装程序。若缺原生样本，先补样本；STEP 不能替代本次验证。
- 新建一个结果目录，建议 `Documents\GongKeProbeResults`。不要将原生工程放入探针包中。

## 第一次运行

1. 用 SOLIDWORKS 打开样本零件和关联工程图。让零件处于活动状态，选好要读取的配置，**单击选中一个已有尺寸**。无需修改尺寸、切换显示设置或清空选择。若未能选到尺寸，仍可运行并带回 `selected_target` 缺失的问题。
2. 截图记录当前配置、目标尺寸读数、标题栏未保存标记。将“帮助 → 关于 SOLIDWORKS”的版本/SP 填入 `field-checklist.txt`。版本接口还会记录原始 `RevisionNumber`。
3. 在“工具 → 宏 → 新建”创建宏，保存为结果目录中的新 `.swp`。在 VBA 编辑器选择“文件 → 导入文件”，导入 `CollectCurrentPart.bas`。打开该模块，选择“调试 → 编译 VBAProject”。本包提供的是源码；这里编译成功才算有编译证据。
4. 如果编译失败，**停止运行**，截图完整错误和高亮代码行，在清单中记录。不要自行删除代码、放宽宏安全设置或安装其他组件。把错误带回即可继续修复。
5. 编译成功后，将光标置于导入模块的 `Public Sub main()` 中运行。输入一个尚不存在的输出路径，如 `C:\Users\你的账户\Documents\GongKeProbeResults\baseline.json`。默认路径在 `%TEMP%`，可在文件管理器地址栏输入 `%TEMP%` 找到。取消输入不会采集。
6. 运行后检查零件和图纸是否仍停留在原配置、原选择和原尺寸，未保存标记是否改变。不要为了证明“不变”而关闭重开或保存，先截图当前内存状态。
7. 保存新生成的 JSON、现场清单和截图。`partial` 是需要核对的真实结果；`collected` 只表示本轮已读记录字段齐备，均不表示工程正确或完整枚举。

宏使用当前 SOLIDWORKS 实例；不启动另一实例、不改尺寸/显示/选择/配置、不重建、不保存 CAD。只在输入的新路径写 JSON，已有文件拒绝覆盖。采集范围是该实例的活动零件与已经打开的工程图，不搜索磁盘或打开其他文件。

## 有时间再做的对照

先完成基线，再在**专用测试副本**上逐项验证；不要改借用电脑上他人的原件。

| 场景 | 带回的证据 | 期待观察 |
| --- | --- | --- |
| 同一参数在两个视图显示 | JSON、两个标注截图及人工对应说明 | 两个显示实例分别存在，不只取第一个 |
| 已有未保存手改 | 运行前后尺寸和未保存标记截图、JSON | 宏不保存或丢弃手改；保存标志相同只是有限证据 |
| 另一个配置的视图 | JSON 与配置截图 | 不算作当前配置的目标实例 |
| 另一目录同名零件 | JSON 与完整引用路径对照 | 不按文件名误配 |
| 已有数值覆盖标注 | JSON 与属性面板截图 | `override=true`；覆盖值保留 API 原值，单位未认定 |
| 已有悬空标注 | JSON 与标注截图 | `dangling=true`，读取失败保留 null/partial |
| 整段文字覆盖 | JSON 与属性面板截图 | 当前版本明确未检查，不能按“未发现问题”放行 |

负例由熟悉 SOLIDWORKS 的操作者在隔离副本中准备，记录所做改变。宏不会制造负例。第一次借机不要求完成写入/Undo 流程。

若需要核对磁盘文件不变，可在运行前后用 Windows PowerShell 对同一组明确的零件/图纸执行 `Get-FileHash -Algorithm SHA256 -LiteralPath '文件的完整路径'`，把结果记入清单。文件 hash 不证明未保存的内存编辑不变，仍需前后界面对照。

## 带回开发机

只需 `*.json`、填好的 `field-checklist.txt` 和截图。编译失败时带回错误和高亮行，无 JSON 也可诊断。原生工程如需进一步分析，单独确认可提供的样本范围，不默认打包上传。

在有 Python 3.10+ 的 Mac/Linux/Windows 运行包内检查器，无第三方依赖：

```sh
python3 read_capture.py /absolute/path/baseline.json
```

仓库内的命令为：

```sh
python tools/solidworks/read_capture.py /absolute/path/baseline.json
```

退出 0 **仅代表 JSON 契约可解析**；必须看 `status`、`findings`、`issues` 和 `unknown`。检查器定位已读到的数值覆盖、悬空及不完整标注，并列出路径/配置/原始尺寸标识均匹配的显示实例。它始终保留 `drawing_review=incomplete`。重复运行、解析成功和合成测试都不能替代现场对照。

## v2 采集内容

- `host.revision_number`：宿主原始版本，现场补记年份/SP。版本适用范围需由对应版本的实测确定。
- `document`：活动文档路径、标题、类型和配置。只有零件可标记 `collected/partial`；其他活动文档为 `unsupported`。
- `selected_target`：单个明确选中的尺寸 FullName、系统值、参数类型、单位和显示类型。半径/直径由显示类型作线索，轴段角色仍未映射；倒角含两个参数，不能作单一目标。选择读取不改变原选择。
- `dimensions`：特征枚举的原始尺寸、系统值、`DrivenState` 与 `ReadOnly`。线性为 m，角度为 rad，整数为 integer。没有补材料、载荷或轴段；`ReadOnly=false` 不等于允许写入。
- `open_drawings[].views[]`：尝试读取已有图纸各页中的视图及其实际模型路径、配置引用；同一参数可以有多个 `display_dimensions` 实例，实际覆盖仍待实测。记录标注名称、关联 FullName、显示类型、数值覆盖与悬空状态。覆盖数值保留 API 原值，单位、公差、整段文字覆盖、手工注释和视图是否更新均未核验。
- `state_before/state_after`：已打开文档的路径、配置、保存标志和选择数量。差异作为问题；相同不证明所有内存/磁盘内容不变，因此 `state_preservation=not_established`。
- `prototype_validation=unverified`、`enumeration_completeness=not_established`、`engineering_semantics=unmapped`：独立的未验收边界，不因 JSON 可读而改变。没有枚举的区域和未知项不计作通过。

新宏与检查器只接受 v2；旧现场文件保留原样，不转换成新证据。当前方案不检查方程、设计表、轻量/分离图纸或全部依赖，不授予任何写入资格。JSON 使用 ASCII 加 Unicode 转义，中文名称可恢复。

开发者可生成独立包：`python tools/package_solidworks_probe.py --out /absolute/path/new-probe.zip`。目标必须不存在；压缩包只含此目录的明确文件和 hash 清单。

## 公开 API 依据

- [RevisionNumber](https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~RevisionNumber.html) 与 [GetSaveFlag](https://help.solidworks.com/2022/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~GetSaveFlag.html)：版本与有限的未保存状态观察。
- [GetSelectedObject6](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.iselectionmgr~getselectedobject6.html)、[swSelectType_e](https://help.solidworks.com/2026/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swSelectType_e.html)、[Type2](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IDisplayDimension~Type2.html)：选中尺寸返回显示实例，类型 14 为尺寸；显示类型与原始参数类型分开。
- [GetFirstDisplayDimension5](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IView~GetFirstDisplayDimension5.html)、[GetNext5](https://help.solidworks.com/2015/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IDisplayDimension~GetNext5.html)：图纸显示实例遍历，一个模型尺寸可显示多次。
- [GetOverride](https://help.solidworks.com/2024/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDisplayDimension~GetOverride.html)、[GetOverrideValue](https://help.solidworks.com/2024/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IDisplayDimension~GetOverrideValue.html)、[GetAnnotation](https://help.solidworks.com/2010/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDisplayDimension~GetAnnotation.html)、[IsDangling](https://help.solidworks.com/2013/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IAnnotation~IsDangling.html)、[GetName](https://help.solidworks.com/2013/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IAnnotation~GetName.html)：数值覆盖、悬空与定位。
- [GetDimension2](https://help.solidworks.com/2019/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.idisplaydimension~getdimension2.html)、[GetSystemValue3 官方示例](https://help.solidworks.com/2012/english/api/sldworksapi/Change_Dimensions_of_Gear_Mate_Example_VB.htm)、[API 单位](https://help.solidworks.com/2024/english/api/sldworksapiprogguide/Overview/Units.htm)：原模型尺寸和系统值。
- [GetNextDisplayDimension](https://help.solidworks.com/2024/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeature~GetNextDisplayDimension.html)、[GetDocuments](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.ISldWorks~GetDocuments.html)、[GetViews](https://help.solidworks.com/2016/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDrawingDoc~GetViews.html)：当前模型和已打开图纸枚举。

以上是公开文档依据，不是本原型的编译或实机验证结果。
