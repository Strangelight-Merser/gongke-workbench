import {
  accessSync,
  constants,
  existsSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join, win32, posix } from "node:path";
import type { AgentSettings, StdioCommand } from "./types.cjs";

export function resolveCommand(
  command: string,
  env: NodeJS.ProcessEnv = process.env,
  platform = process.platform,
) {
  const path = platform === "win32" ? win32 : posix;
  const directories = (env.PATH || env.Path || "").split(path.delimiter).filter(Boolean);
  if (platform === "darwin")
    directories.push("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin");
  const candidates = path.isAbsolute(command)
    ? [command]
    : directories.flatMap((dir) =>
        platform === "win32"
          ? [command, ...(/\.[^\\/]+$/.test(command) ? [] : [command + ".exe", command + ".cmd", command + ".bat"])].map((name) => path.join(dir, name))
          : [path.join(dir, command)],
      );
  for (const file of candidates) {
    try {
      accessSync(file, platform === "win32" ? constants.F_OK : constants.X_OK);
      return path.resolve(file);
    } catch {
      /* 继续检索 PATH */
    }
  }
  throw new Error(`找不到可执行文件：${command}，请在连接设置中填写绝对路径`);
}
export function validateSettings(value: AgentSettings) {
  const command = (v: StdioCommand) => {
    if (
      !v ||
      typeof v.command !== "string" ||
      !v.command.trim() ||
      !Array.isArray(v.args) ||
      v.args.some((x) => typeof x !== "string") ||
      !v.env ||
      typeof v.env !== "object" ||
      Array.isArray(v.env) ||
      Object.values(v.env).some((x) => typeof x !== "string")
    )
      throw new Error("启动配置需要 command、字符串数组 args 和字符串映射 env");
  };
  if (!value || !Array.isArray(value.agents) || !value.agents.length)
    throw new Error("至少配置一个 Agent");
  const ids = new Set<string>();
  for (const agent of value.agents) {
    command(agent);
    if (
      typeof agent.id !== "string" ||
      !agent.id ||
      typeof agent.name !== "string" ||
      !agent.name ||
      ids.has(agent.id)
    )
      throw new Error("Agent 需要唯一 id 和名称");
    ids.add(agent.id);
  }
  command(value.mcp);
}
export class AgentConfiguration {
  readonly path: string;
  constructor(
    private directory: string,
    private root: string,
    private serviceExecutable?: string,
  ) {
    this.path =
      process.env.GONGKE_AGENT_CONFIG || join(directory, "agents.json");
  }
  read(): AgentSettings {
    if (existsSync(this.path)) {
      const settings = JSON.parse(readFileSync(this.path, "utf8"));
      validateSettings(settings);
      return settings;
    }
    const patch = join(this.directory, "deepseek-engineering.patch.yml");
    writeFileSync(
      patch,
      `- insert:\n    - id: gongke-engineering-policy\n      name: ${JSON.stringify(join(__dirname, "deepseek-policy.cjs"))}\n- id: tools\n  config:\n    mode: native\n- id: approval\n  config:\n    policy: ask\n`,
    );
    return {
      agents: [
        {
          id: "deepseek",
          name: "DeepSeek Harness",
          command: "dsh",
          args: ["--profile", "acp", "--patch", patch],
          env: {},
        },
        {
          id: "opencode",
          name: "OpenCode",
          command: "opencode",
          args: ["acp"],
          env: {
            OPENCODE_CONFIG_CONTENT: JSON.stringify({
              permission: { "*": "deny", "gongke_*": "ask" },
              default_agent: "gongke",
              agent: {
                gongke: {
                  mode: "primary",
                  description: "构想引擎工程任务",
                  prompt:
                    "通过 gongke 工程工具读取和操作工程。所有工程事实均以工具结果为准。",
                  permission: { "*": "deny", "gongke_*": "ask" },
                },
              },
            }),
          },
        },
      ],
      mcp: {
        command: this.serviceExecutable || process.env.GONGKE_PYTHON || "python3",
        args: [
          ...(this.serviceExecutable ? [] : ["-m", "gongke_app"]),
          "mcp",
          "--state-dir", join(this.directory, "state"),
          "--project", "${project}",
        ],
        env: this.serviceExecutable
          ? {}
          : { PYTHONPATH: this.root, PYTHONUNBUFFERED: "1" },
      },
    };
  }
  save(settings: AgentSettings) {
    validateSettings(settings);
    writeFileSync(this.path, JSON.stringify(settings, null, 2), {
      mode: 0o600,
    });
  }
  launch(id: string, project: string) {
    const settings = this.read();
    const profile = settings.agents.find((a) => a.id === id);
    if (!profile) throw new Error("未找到此 Agent 配置");
    const expand = (value: StdioCommand): StdioCommand => {
      const env = Object.fromEntries(
        Object.entries(value.env).map(([name, text]) => [
          name,
          text.replaceAll("${project}", project),
        ]),
      );
      return {
        command: resolveCommand(value.command, { ...process.env, ...env }),
        args: value.args.map((text) => text.replaceAll("${project}", project)),
        env,
      };
    };
    return {
      profile: { ...profile, ...expand(profile) },
      mcp: expand(settings.mcp),
    };
  }
}
