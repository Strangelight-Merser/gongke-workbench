const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  normalizeProvider,
  mayReuseKey,
} = require("../dist-electron/credentials.cjs");
test("更换服务地址不能自动复用已保存的密钥", () => {
  assert.equal(
    mayReuseKey("https://api.openai.com/v1", "https://unrelated.example/v1"),
    false,
  );
  assert.equal(
    mayReuseKey(
      "https://host.example/team-one",
      "https://host.example/team-two",
    ),
    false,
  );
  assert.equal(
    mayReuseKey("https://api.openai.com/v1", "https://api.openai.com/v1/"),
    true,
  );
  assert.throws(() => normalizeProvider("file:///etc/passwd"));
  assert.throws(() => normalizeProvider("https://user:secret@example.com/v1"));
});
