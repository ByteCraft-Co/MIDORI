const test = require("node:test");
const assert = require("node:assert/strict");

const { buildKeywordCompletionItems } = require("../src/lsp/completion");
const { KEYWORDS } = require("../src/lsp/lexicon");

test("keyword completion contains all canonical keywords", () => {
  const items = buildKeywordCompletionItems("", {
    fuzzyEnabled: true,
    maxEditDistance: 2,
  });

  for (const keyword of KEYWORDS) {
    assert.ok(items.has(keyword), `missing keyword completion for ${keyword}`);
  }
});

test("fuzzy keyword completion flags typo suggestions", () => {
  const items = buildKeywordCompletionItems("retrun", {
    fuzzyEnabled: true,
    maxEditDistance: 2,
  });

  const item = items.get("return");
  assert.ok(item);
  assert.equal(item.detail, "MIDORI keyword suggestion");
});

test("prefix completion keeps direct keyword matches", () => {
  const items = buildKeywordCompletionItems("im", {
    fuzzyEnabled: true,
    maxEditDistance: 2,
  });

  assert.ok(items.get("import"));
  assert.ok(items.get("impl"));
});