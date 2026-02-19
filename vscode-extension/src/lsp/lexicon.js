const keywordData = require("./data/compiler-keywords.json");

const KEYWORDS = Object.freeze([...keywordData.keywords]);

const TYPE_NAMES = Object.freeze([
  "Int",
  "Float",
  "Bool",
  "Char",
  "String",
  "Void",
  "Option",
  "Result",
]);

const BUILTIN_FUNCTIONS = Object.freeze([
  {
    name: "print",
    params: [{ name: "value", type: "Int | Float | Bool | Char | String" }],
    returnType: "Void",
    documentation: "Print a scalar or string value.",
  },
  {
    name: "read_file",
    params: [{ name: "path", type: "String" }],
    returnType: "Result[String, String]",
    documentation: "Read a file from disk and return Result[String, String].",
  },
  {
    name: "Some",
    params: [{ name: "value", type: "T" }],
    returnType: "Option[T]",
    documentation: "Construct Option present value.",
  },
  {
    name: "None",
    params: [],
    returnType: "Option[T]",
    documentation: "Construct Option absent value.",
  },
  {
    name: "Ok",
    params: [{ name: "value", type: "T" }],
    returnType: "Result[T, E]",
    documentation: "Construct Result success value.",
  },
  {
    name: "Err",
    params: [{ name: "error", type: "E" }],
    returnType: "Result[T, E]",
    documentation: "Construct Result error value.",
  },
]);

const BUILTIN_FUNCTION_MAP = new Map(BUILTIN_FUNCTIONS.map((item) => [item.name, item]));

const KEYWORD_DOCS = Object.freeze({
  fn: "Declare a function.",
  let: "Declare an immutable local binding.",
  var: "Declare a mutable local binding.",
  struct: "Declare a nominal product type.",
  enum: "Declare a tagged union type.",
  trait: "Declare an interface-like method contract.",
  impl: "Reserved for trait/type implementation blocks.",
  pub: "Mark an item as public.",
  use: "Reserved for named imports/aliases.",
  module: "Reserved for explicit module declarations.",
  import: "Import another .mdr file at top level.",
  if: "Branch on a condition.",
  else: "Alternative branch for if expressions.",
  match: "Pattern-match a value across arms.",
  for: "Reserved for iterator loops.",
  in: "Reserved for membership/range iteration.",
  while: "Reserved for while loops.",
  loop: "Reserved for infinite loop blocks.",
  break: "Exit the nearest loop.",
  continue: "Skip to the next loop iteration.",
  return: "Return from the current function.",
  task: "Mark a function as asynchronous task entry.",
  spawn: "Reserved for async task spawn expression.",
  await: "Await task completion in expression context.",
  unsafe: "Mark a block as unsafe operations context.",
  extern: "Declare an external function signature.",
  error: "Declare a custom error kind.",
  raise: "Raise a custom error in Result-returning functions.",
  true: "Boolean true literal.",
  false: "Boolean false literal.",
});

function isKeyword(value) {
  return KEYWORDS.includes(value);
}

function getKeywordDoc(value) {
  return KEYWORD_DOCS[value] || null;
}

module.exports = {
  KEYWORDS,
  TYPE_NAMES,
  BUILTIN_FUNCTIONS,
  BUILTIN_FUNCTION_MAP,
  KEYWORD_DOCS,
  isKeyword,
  getKeywordDoc,
};