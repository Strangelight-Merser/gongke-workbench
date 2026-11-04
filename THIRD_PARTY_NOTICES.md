# 第三方来源

## DeepSeek Harness：Agent 对话展示参考

- 来源：https://github.com/deepseek-ai/deepseek-harness
- 研究版本：`8bd073392eef6f54e921a093b95076248eb08cbb`
- 许可：MIT，Copyright (c) 2026 DeepSeek。
- 参考文件：`packages/client/ui-tool/src/client/tool/components/ToolRow.tsx`、`ToolRow.module.css`、`toolviews/GenericToolCard.tsx`、`ToolCallTree.tsx`；`packages/client/ui-chat/src/client/chat/ReasoningRow.tsx` 与 `model/tool-call-tree.ts`。
- 本项目独立实现紧凑工具行、折叠详情、限高输出和独立思考区域，未复制组件源码、样式源码或引入 DSH 依赖。连续成功步骤分组是本项目针对工程任务的设计。实现位于 `desktop/src/agent/ToolCall.tsx`、`events.ts` 和 `desktop/src/styles/agent.css`。
- 若后续直接复制上游实现，需在复用文件头保留版权和许可声明；下列为本次所读上游许可全文。

MIT License

Copyright (c) 2026 DeepSeek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
