# 原生轴与图纸基准

这些 FCStd 是 `tests/e2e/revision_fixture.py` 在 FreeCAD 1.1.4 中人工构造的三段轴及两视图直径标注。它们不代表学生样本；载荷、材料和限值是明确的教学假定，不可当作实际设计依据。`manifest.json` 记录原文件 hash 与预期结果。

| 文件 | 用途 |
| --- | --- |
| normal.FCStd | 两处目标直径均为 38 mm |
| override.FCStd | 第一处标注启用任意显示值 99 mm |
| wrong_reference.FCStd | 第一视图指向外观相同的另一对象 |
| dangling.FCStd | 第一处标注引用不存在的 Edge999 |
| missing_condition.FCStd | 正常图纸；对应 case 缺少弹性模量，应力保留、挠度不计算 |

复制要试用的 FCStd 和同名 case.json 到一个新的工作目录。将 case 的 `document.path` 改为副本的绝对路径，其他映射保持原样。打开该 FCStd，在原生 CAD 中打开 `ShaftDrawing` 并完成更新，再启用工科工作台。运行：

```sh
python -m gongke_core inspect-revision --host freecad \
  --case /absolute/path/normal.case.json --out /absolute/path/new-result
```

必须在 FreeCAD 所在的机器上执行实时入口，或明确配置其本机桥接端点。不要把另一机器上的同名文件当作当前工程。`--capture` 仅用于离线证据重放。

保存的图纸重开后，投影缓存可能尚未生成；这时读取器报告未知，不自动刷新或重算。手工修复负例后，重新检查可得到新的结论。不要修改这里的基准来消除失败。

开发验证脚本 `tests/e2e/revision_inventory_macro.py` 会重开每份工程，并在读取前后核对文件 hash、修改标志、事务、撤销栈、选择、编辑状态及已记录的对象属性。该脚本只用于隔离测试副本。
