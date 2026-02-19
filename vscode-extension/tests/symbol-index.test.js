const test = require("node:test");
const assert = require("node:assert/strict");
const { TextDocument } = require("vscode-languageserver-textdocument");

const { buildSymbolIndex } = require("../src/lsp/symbol-index");

test("symbol index includes struct fields and trait methods", () => {
  const source = [
    "struct User {",
    "  id: Int,",
    "  name: String,",
    "}",
    "",
    "trait Display {",
    "  fn render(value: String) -> String",
    "}",
    "",
    "fn main() -> Int {",
    "  let user_id := 1",
    "  user_id",
    "}",
  ].join("\n");

  const doc = TextDocument.create("file:///workspace/test.mdr", "midori", 0, source);
  const index = buildSymbolIndex(doc);

  assert.ok(index.structs.some((s) => s.name === "User"));
  assert.ok(index.structFields.some((s) => s.name === "id" && s.container === "User"));
  assert.ok(index.structFields.some((s) => s.name === "name" && s.container === "User"));

  assert.ok(index.traits.some((s) => s.name === "Display"));
  assert.ok(index.traitMethods.some((s) => s.name === "render" && s.container === "Display"));

  assert.ok(index.functions.some((s) => s.name === "main"));
  assert.ok(index.locals.some((s) => s.name === "user_id" && s.container === "main"));
});