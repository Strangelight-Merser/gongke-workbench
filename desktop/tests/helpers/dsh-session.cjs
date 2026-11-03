// dsh 会话由多个独立 Zstd 帧追加组成；每帧均解压，不能只读首帧元数据。
const fs = require("node:fs");
const path = require("node:path");
const { homedir } = require("node:os");
const { zstdDecompressSync } = require("node:zlib");
const { createHash } = require("node:crypto");
const { redactRecord } = require("../../dist-electron/acp/diagnostics.cjs");

function decodeZstdFrames(bytes) {
  const frames = [];
  let offset = 0;
  while (offset < bytes.length) {
    const decoded = zstdDecompressSync(bytes.subarray(offset), { info: true });
    const consumed = decoded.engine.bytesWritten;
    if (!Number.isInteger(consumed) || consumed <= 0)
      throw Error(`Zstd 解码未推进：byte ${offset}`);
    offset += consumed;
    frames.push(decoded.buffer);
  }
  return Buffer.concat(frames);
}

function summarizeUsage(events) {
  const groups = {};
  for (const event of events) {
    const group = (groups[event.type] ||= { count: 0, tokens: {} });
    group.count++;
    for (const field of [
      "inputTokens",
      "outputTokens",
      "cacheReadTokens",
      "cacheWriteTokens",
      "totalTokens",
    ]) {
      if (typeof event.usage[field] === "number")
        group.tokens[field] = (group.tokens[field] || 0) + event.usage[field];
    }
  }
  return groups;
}

function collectDshSession(sessionId, directory) {
  if (!sessionId || !/^[a-zA-Z0-9-]+$/.test(sessionId))
    return { available: false, reason: "无有效 session id" };
  const sessions =
    process.env.GONGKE_DSH_SESSIONS || path.join(homedir(), ".dsh/sessions");
  const files = fs
    .globSync(`*/${sessionId}/session.v*.jsonl*`, { cwd: sessions })
    .filter((f) => /session\.v\d+\.jsonl(?:\.zstd)?$/.test(f))
    .sort(
      (a, b) =>
        Number(b.match(/session\.v(\d+)/)[1]) -
        Number(a.match(/session\.v(\d+)/)[1]),
    );
  if (!files.length)
    return { available: false, reason: "未找到本会话的持久化记录", sessions };
  const file = path.join(sessions, files[0]);
  const bytes = fs.readFileSync(file);
  const content = file.endsWith(".zstd")
    ? decodeZstdFrames(bytes).toString("utf8")
    : bytes.toString("utf8");
  const rows = content.trim().split("\n").map(JSON.parse);
  fs.writeFileSync(
    path.join(directory, "dsh-session.jsonl"),
    rows.map((row) => JSON.stringify(redactRecord(row))).join("\n") + "\n",
  );
  const usage = rows
    .filter((row) => row.data?.usage)
    .map((row) => ({
      type: row.type,
      turn: row.data.turn,
      step: row.data.step,
      source: row.data.message?.source,
      usage: row.data.usage,
    }));
  return {
    available: true,
    source: file,
    source_sha256: createHash("sha256").update(bytes).digest("hex"),
    source_bytes: bytes.length,
    usage,
    usage_available: usage.length > 0,
    records: rows.length,
    usage_by_event_type: summarizeUsage(usage),
    note: "原样记录顶层事件用量，不重复累加内嵌 stream；attempt/compaction 与正常消息分别保留。未报告金额时费用为未知。",
  };
}

module.exports = { collectDshSession, decodeZstdFrames, summarizeUsage };
