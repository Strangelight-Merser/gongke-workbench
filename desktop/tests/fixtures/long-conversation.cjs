// 确定性 Agent 状态替身；不连接模型，不执行 CAD 写操作。
exports.conversation = () => {
  const events = [
    { type: "user", text: "按图纸建立支架，保留特征树，检查安装孔。" },
    {
      type: "update",
      update: {
        sessionUpdate: "agent_message_chunk",
        content: {
          type: "text",
          text: "先建立底板和立板，再切安装孔。尺寸按图纸 mm 换算；以下为界面验收替身。",
        },
      },
    },
    {
      type: "update",
      update: {
        sessionUpdate: "agent_thought_chunk",
        content: {
          type: "text",
          text:
            "先核对基准和平面。\n\n" +
            "保留草图约束，检查每个特征的依赖关系。".repeat(80),
        },
      },
    },
  ];
  const call = (id, status, input, output, title = "host.feature") =>
    events.push({
      type: "update",
      update: {
        sessionUpdate: "tool_call",
        toolCallId: id,
        title,
        kind: "edit",
        status,
        rawInput: input,
        rawOutput: output,
      },
    });
  for (let i = 0; i < 32; i++)
    call(
      "step-" + i,
      "completed",
      {
        feature: {
          kind: i % 2 ? "hole" : "pad",
          ...(i % 2
            ? { diameter: 0.014, through_all: true }
            : { length: 0.008 }),
        },
        ...(i === 1 ? {} : { name: i === 0 ? "底板拉伸" : "支架特征 " + i }),
        geometry: Array.from({ length: 80 }, (_, n) => ({
          kind: "line",
          start: [n, 0],
          end: [n, 1],
        })),
      },
      {
        native_ref: "Feature" + i,
        message: "已更新原生特征",
        diagnostic: "几何回执\n".repeat(160),
      },
    );
  call(
    "failed",
    "failed",
    { feature: { kind: "fillet", radius: 0.002 } },
    { error: { message: "圆角半径超过相邻边间距，请减小半径后重试。" } },
  );
  call(
    "retry",
    "completed",
    { feature: { kind: "fillet", radius: 0.001 } },
    { native_ref: "Fillet", message: "半径改为 1 mm，重建完成。" },
  );
  call(
    "check",
    "completed",
    { conditions: [{ id: "hole", expected: 0.014 }] },
    {
      status: "fail",
      checks: [
        {
          id: "hole",
          status: "fail",
          expected: 0.014,
          actual: 0.012,
          unit: "m",
          message: "安装孔直径不符",
        },
        {
          id: "base",
          status: "pass",
          expected: 0.008,
          actual: 0.008,
          unit: "m",
        },
      ],
    },
    "host.check",
  );
  call(
    "save",
    "pending",
    { path: "bracket.FCStd" },
    undefined,
    "host.model_save",
  );
  events.push({
    type: "permission",
    id: "save-permission",
    request: {
      toolCall: {
        toolCallId: "save",
        title: "保存支架工作副本",
        rawInput: { path: "bracket.FCStd" },
      },
      options: [
        { optionId: "yes", kind: "allow_once", name: "Allow" },
        { optionId: "no", kind: "reject_once", name: "Reject" },
      ],
    },
  });
  return events;
};
