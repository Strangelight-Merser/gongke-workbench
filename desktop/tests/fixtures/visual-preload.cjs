const { contextBridge } = require("electron");
const projectPath = "C:/Course/bracket";
const drawing = `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700" viewBox="0 0 1000 700"><rect width="1000" height="700" fill="white"/><g fill="none" stroke="#242424" stroke-width="2"><rect x="36" y="36" width="928" height="628"/><path d="M180 450 V210 H300 V350 H570 V450 Z"/><circle cx="240" cy="270" r="30"/><circle cx="420" cy="400" r="25"/><path d="M680 210 H800 V450 H680 Z M680 350 H800 M680 400 H800"/><path stroke-width="1" d="M180 480 V520 M570 480 V520 M180 500 H570 M150 210 H110 M150 450 H110 M130 210 V450"/><path d="M180 500 l10 -4 m-10 4 l10 4 M570 500 l-10 -4 m10 4 l-10 4"/><rect x="610" y="560" width="354" height="104"/><path d="M610 600 H964 M610 632 H964 M770 600 V664"/></g><g fill="#242424" font-family="sans-serif" font-size="18"><text x="340" y="492">120</text><text x="94" y="340">80</text><text x="220" y="320">⌀20</text><text x="400" y="445">⌀12</text><text x="635" y="587">支架 · 建模练习</text><text x="626" y="622">材料：45钢</text><text x="785" y="622">比例 1:1</text><text x="626" y="654">界面评审样例</text><text x="785" y="654">A4 · 01</text></g></svg>`;
function simplePdf() {
  const stream =
    "0.5 w 30 30 535 782 re S 100 250 m 100 600 l 180 600 l 180 350 l 450 350 l 450 250 l h S 100 200 m 450 200 l S BT /F1 16 Tf 240 180 Td (120 mm) Tj ET BT /F1 20 Tf 70 740 Td (BRACKET - DRAWING FIXTURE) Tj ET BT /F1 12 Tf 70 65 Td (Visual review only - not an engineering drawing) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let text = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((o, i) => {
    offsets.push(text.length);
    text += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const at = text.length;
  text += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((n) => String(n).padStart(10, "0") + " 00000 n \n")
    .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${at}\n%%EOF`;
  return text;
}
const dxf = [
  "0",
  "SECTION",
  "2",
  "HEADER",
  "9",
  "$ACADVER",
  "1",
  "AC1027",
  "0",
  "ENDSEC",
  "0",
  "SECTION",
  "2",
  "ENTITIES",
  ...[
    [0, 0, 120, 0],
    [120, 0, 120, 30],
    [120, 30, 40, 30],
    [40, 30, 40, 80],
    [40, 80, 0, 80],
    [0, 80, 0, 0],
  ].flatMap(([x, y, a, b]) => [
    "0",
    "LINE",
    "8",
    "0",
    "10",
    x,
    "20",
    y,
    "11",
    a,
    "21",
    b,
  ]),
  "0",
  "CIRCLE",
  "8",
  "0",
  "10",
  "20",
  "20",
  "55",
  "40",
  "10",
  "0",
  "TEXT",
  "8",
  "0",
  "10",
  "55",
  "20",
  "-12",
  "40",
  "6",
  "1",
  "120 mm",
  "0",
  "ENDSEC",
  "0",
  "EOF",
].join("\n");
const files = [
  { path: "inputs/bracket.pdf", name: "支架图纸.pdf", kind: "pdf" },
  { path: "inputs/bracket.svg", name: "支架图纸.svg", kind: "svg" },
  { path: "inputs/bracket.dxf", name: "支架图纸.dxf", kind: "dxf" },
];
let scenario = "empty",
  agentListeners = [],
  onboardingListeners = [],
  events = [],
  embedListeners = [];
let project = {
  path: projectPath,
  name: "支架建模练习",
  files: [],
  task: null,
  generations: [],
};
let agent = {
  phase: "ready",
  project: projectPath,
  agentId: "deepseek",
  authMethods: [],
  events: [],
};
const settings = {
  agents: [
    {
      id: "deepseek",
      name: "DeepSeek Harness",
      command: "dsh",
      args: ["--profile", "acp"],
      env: {},
    },
  ],
  mcp: {
    command: "gongke-service",
    args: ["mcp", "--project", projectPath],
    env: {},
  },
};
const selections = [];
const modelContext = {
  session_id: "fixture-session",
  document: "Bracket",
  path: projectPath + "/models/bracket.FCStd",
  revision: 4,
  objects: [],
  unbound_objects: [],
  selection: [],
  unbound_selection: [],
};
const target = (object_name) => ({
  host: "freecad",
  session_id: modelContext.session_id,
  document_path: modelContext.path,
  expected_revision: 4,
  object_name,
});
const onboarding = () => ({
  selected: "deepseek",
  agents: {
    deepseek: {
      step: scenario === "onboarding" ? "credentials" : "complete",
      command: "dsh",
      project: projectPath,
    },
    workbuddy: { step: "detect" },
  },
  releases: [
    {
      provider: "deepseek",
      version: "1.0",
      url: "https://example.invalid",
      size: 0,
      sha512: "",
      signerThumbprint: "",
    },
  ],
  canInstall: false,
});
const emit = () => agentListeners.forEach((f) => f(agent));
contextBridge.exposeInMainWorld("gongke", {
  platform: "win32",
  request: async (method, params = {}) => {
    if (method === "system.status") return { ready: true };
    if (
      method === "project.current" ||
      method === "project.open" ||
      method === "project.create"
    )
      return project;
    if (method === "hosts.list")
      return [{ host: "freecad", host_id: "fixture", connected: true }];
    if (method === "freecad.context") return modelContext;
    if (method === "host.context") return {active_document: {
      host_instance:"fixture", document_id:modelContext.session_id, revision:4, configuration:""
    }, documents:[]};
    if (method === "freecad.scene") return {...modelContext, objects:[], pages:[]};
    if (method === "freecad.select") {
      if (
        params.session_id !== modelContext.session_id ||
        params.expected_revision !== 4
      )
        throw new Error("样例对象身份不匹配");
      selections.push(params);
      return { ...modelContext, selected_object: params.object_name };
    }
    if (method === "task.list")
      return scenario === "checks"
        ? [
            {
              task_id: "review-fixture",
              kind: "revision.inspect",
              title: "支架图纸检查",
              status: "complete",
              project: projectPath,
              result: {
                checks: [
                  {
                    item: "安装孔直径",
                    ok: false,
                    detail: "图纸为 12 mm，模型读数为 10 mm",
                    expected: 12,
                    actual: 10,
                    unit: "mm",
                    target: target("Hole002"),
                  },
                  {
                    item: "底座总长",
                    ok: true,
                    detail: "图纸与模型均为 120 mm",
                    expected: 120,
                    actual: 120,
                    unit: "mm",
                    target: target("BasePad"),
                  },
                  {
                    item: "立板厚度",
                    ok: true,
                    detail: "图纸与模型均为 8 mm",
                    expected: 8,
                    actual: 8,
                    unit: "mm",
                    target: target("UprightPad"),
                  },
                ],
              },
            },
          ]
        : [];
    if (method === "design.calculate")
      return {
        checks: [
          {
            item: "安装孔直径",
            ok: false,
            detail: "图纸要求 12 mm；模型为 10 mm",
          },
          { item: "底座长度", ok: true, detail: "图纸与模型均为 120 mm" },
        ],
      };
    if (method === "project.read_file") return { content: drawing };
    if (method === "task.get") return { receipts: [] };
    throw new Error("视觉样例不执行工程命令：" + method);
  },
  chooseProject: async () => projectPath,
  reveal: async () => {},
  restart: async () => ({}),
  onEvent: (f) => {
    events.push(f);
    return () => {
      events = events.filter((x) => x !== f);
    };
  },
  documents: {
    import: async () => files,
    read: async (path) =>
      path.endsWith(".pdf")
        ? {
            mime: "application/pdf",
            content: Buffer.from(simplePdf()).toString("base64"),
          }
        : path.endsWith(".dxf")
          ? {
              mime: "application/dxf",
              content: Buffer.from(dxf).toString("base64"),
            }
          : {
              mime: "image/svg+xml",
              content: Buffer.from(drawing).toString("base64"),
            },
  },
  getAgentMode: async () => "model",
  setAgentMode: async () => {},
  agent: {
    settings: async () => settings,
    saveSettings: async () => {},
    state: async () => agent,
    start: async () => {
      agent = { ...agent, phase: "ready" };
      emit();
    },
    authenticate: async () => {},
    newSession: async () => {
      agent = { ...agent, events: [] };
      emit();
    },
    prompt: async (text) => {
      agent = {
        ...agent,
        phase: "prompting",
        events: [...agent.events, { type: "user", text }],
      };
      emit();
    },
    cancel: async () => {
      agent = { ...agent, phase: "ready" };
      emit();
    },
    disconnect: async () => {
      agent = { ...agent, phase: "disconnected" };
      emit();
    },
    permission: async (id, option) => {
      agent = { ...agent, events: [...agent.events, { type: "permission-resolved", id, option }] };
      emit();
    },
    onState: (f) => {
      agentListeners.push(f);
      return () => {
        agentListeners = agentListeners.filter((x) => x !== f);
      };
    },
  },
  onboarding: {
    state: async () => onboarding(),
    act: async () => onboarding(),
    onState: (f) => {
      onboardingListeners.push(f);
      return () => {
        onboardingListeners = onboardingListeners.filter((x) => x !== f);
      };
    },
  },
});
contextBridge.exposeInMainWorld("cadEmbed", {
  supported: true,
  status: async () => ({
    supported: true,
    attached: { hwnd: "fixture", pid: 1, kind: "freecad" },
    mode: "embed",
    pendingPids: [],
  }),
  discover: async () => ({ installations: [], windows: [] }),
  layout: async () => {},
  focus: async () => ({
    supported: true,
    attached: { hwnd: "fixture", pid: 1, kind: "freecad" },
    mode: "embed",
    pendingPids: [],
  }),
  cancelClose: () => {},
  onEvent: (f) => {
    embedListeners.push(f);
    return () => {};
  },
});
contextBridge.exposeInMainWorld("visualReview", {
  conversation: (conversation) => {
    agent = { ...agent, phase: "prompting", events: conversation };
    emit();
  },
  selections: () => selections,
  setScenario: (name) => {
    scenario = name;
    project = {
      ...project,
      files: name === "empty" || name === "onboarding" ? [] : files,
    };
    agent = {
      ...agent,
      phase:
        name === "modeling"
          ? "prompting"
          : name === "onboarding"
            ? "disconnected"
            : "ready",
      events:
        name === "modeling"
          ? [
              { type: "user", text: "根据支架图纸建模，保留草图和特征。" },
              {
                type: "update",
                update: {
                  sessionUpdate: "agent_message_chunk",
                  content: {
                    type: "text",
                    text: "已读取图纸。底座长 120 mm，立板高 80 mm。我先建立基体，再添加安装孔和圆角。",
                  },
                },
              },
              {
                type: "update",
                update: {
                  sessionUpdate: "tool_call",
                  toolCallId: "pad",
                  title: "建立基体拉伸",
                  status: "completed",
                  kind: "edit",
                },
              },
              {
                type: "update",
                update: {
                  sessionUpdate: "tool_call",
                  toolCallId: "hole",
                  title: "创建安装孔",
                  status: "in_progress",
                  kind: "edit",
                },
              },
            ]
          : [],
    };
    emit();
    onboardingListeners.forEach((f) => f(onboarding()));
    events.forEach((f) =>
      f({
        event: "task.updated",
        project: projectPath,
        task: { task_id: "scene", project: projectPath, status: "complete" },
      }),
    );
  },
});
