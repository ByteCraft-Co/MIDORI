const test = require("node:test");
const assert = require("node:assert/strict");

const { levenshteinDistance, rankKeywordSuggestions } = require("../src/lsp/fuzzy");
const { KEYWORDS } = require("../src/lsp/lexicon");

test("levenshteinDistance handles basic typo distance", () => {
  assert.equal(levenshteinDistance("retrun", "return"), 2);
  assert.equal(levenshteinDistance("await", "await"), 0);
});

test("rankKeywordSuggestions places return at top for retrun", () => {
  const ranked = rankKeywordSuggestions("retrun", KEYWORDS, 2);
  assert.ok(ranked.length > 0);
  assert.equal(ranked[0].keyword, "return");
});

test("rankKeywordSuggestions includes import and impl for im", () => {
  const ranked = rankKeywordSuggestions("im", KEYWORDS, 2).map((item) => item.keyword);
  assert.ok(ranked.includes("import"));
  assert.ok(ranked.includes("impl"));
});