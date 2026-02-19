const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { fileURLToPath, pathToFileURL } = require("node:url");
const { spawn } = require("node:child_process");
const {
  CompletionItemKind,
  createConnection,
  DiagnosticSeverity,
  InsertTextFormat,
  MarkupKind,
  ProposedFeatures,
  TextDocuments,
  TextDocumentSyncKind,
} = require("vscode-languageserver/node");
const { TextDocument } = require("vscode-languageserver-textdocument");

const connection = createConnection(ProposedFeatures.all);
const documents = new TextDocuments(TextDocument);

let settings = {
  command: "midori",
  args: [],
  runOnType: true,
  debounceMs: 250,
  workspaceRoot: process.cwd(),
};

/** @type {Map<string, NodeJS.Timeout>} */
const timers = new Map();
/** @type {Map<string, number>} */
const versions = new Map();
/** @type {Map<string, {version: number, index: SymbolIndex}>} */
const symbolCache = new Map();
/** @type {Map<string, {mtimeMs: number, index: SymbolIndex}>} */
const externalIndexCache = new Map();

const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const KEYWORDS = [
  "import",
  "error",
  "fn",
  "extern",
  "enum",
  "struct",
  "trait",
  "task",
  "pub",
  "let",
  "var",
  "if",
  "else",
  "match",
  "return",
  "raise",
  "unsafe",
  "spawn",
  "await",
  "true",
  "false",
];
const TYPE_NAMES = ["Int", "Float", "Bool", "Char", "String", "Void", "Option", "Result"];
const BUILTIN_FUNCTIONS = [
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
];
const BUILTIN_FUNCTION_MAP = new Map(BUILTIN_FUNCTIONS.map((item) => [item.name, item]));

/**
 * @typedef {"function" | "param" | "local" | "enum" | "variant" | "error"} SymbolKindTag
 *
 * @typedef {{
 *   name: string,
 *   kind: SymbolKindTag,
 *   uri: string,
 *   offset: number,
 *   range: {start: {line: number, character: number}, end: {line: number, character: number}},
 *   container?: string,
 *   type?: string,
 *   params?: Array<{name: string, type: string}>,
 *   signature?: string,
 *   returnType?: string,
 *   isExtern?: boolean,
 *   bodyStartOffset?: number,
 *   bodyEndOffset?: number,
 * }} MidoriSymbol
 *
 * @typedef {{
 *   uri: string,
 *   imports: Array<{path: string, offset: number}>,
 *   functions: MidoriSymbol[],
 *   enums: MidoriSymbol[],
 *   variants: MidoriSymbol[],
 *   errors: MidoriSymbol[],
 *   params: MidoriSymbol[],
 *   locals: MidoriSymbol[],
 *   topLevelSymbols: MidoriSymbol[],
 *   allSymbols: MidoriSymbol[],
 * }} SymbolIndex
 */

connection.onInitialize((params) => {
  const init = params.initializationOptions || {};
  settings = normalizeSettings(init);
  return {
    capabilities: {
      textDocumentSync: TextDocumentSyncKind.Incremental,
      completionProvider: {
        triggerCharacters: [":", "("],
      },
      hoverProvider: true,
      signatureHelpProvider: {
        triggerCharacters: ["(", ","],
        retriggerCharacters: [","],
      },
      definitionProvider: true,
    },
  };
});

documents.onDidOpen((event) => {
  symbolCache.delete(event.document.uri);
  scheduleValidation(event.document, true);
});

documents.onDidChangeContent((event) => {
  symbolCache.delete(event.document.uri);
  if (!settings.runOnType) {
    return;
  }
  scheduleValidation(event.document, false);
});

documents.onDidSave((event) => {
  symbolCache.delete(event.document.uri);
  scheduleValidation(event.document, true);
});

documents.onDidClose((event) => {
  clearTimer(event.document.uri);
  symbolCache.delete(event.document.uri);
  connection.sendDiagnostics({ uri: event.document.uri, diagnostics: [] });
});

connection.onCompletion(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return [];
  }
  const source = document.getText();
  const offset = document.offsetAt(params.position);
  if (isInsideCommentOrString(source, offset)) {
    return [];
  }

  const index = getOrCreateSymbolIndex(document);
  const completionItems = new Map();

  for (const keyword of KEYWORDS) {
    completionItems.set(keyword, {
      label: keyword,
      kind: CompletionItemKind.Keyword,
    });
  }
  for (const typeName of TYPE_NAMES) {
    completionItems.set(typeName, {
      label: typeName,
      kind: CompletionItemKind.Class,
      detail: "MIDORI type",
    });
  }
  for (const builtin of BUILTIN_FUNCTIONS) {
    completionItems.set(builtin.name, {
      label: builtin.name,
      kind: CompletionItemKind.Function,
      detail: `${builtin.name}(${formatCallableParams(builtin.params)}) -> ${builtin.returnType}`,
      insertText: buildCallSnippet(builtin.name, builtin.params),
      insertTextFormat: InsertTextFormat.Snippet,
      documentation: {
        kind: MarkupKind.Markdown,
        value: builtin.documentation,
      },
    });
  }

  for (const symbol of getSymbolsInScope(index, offset)) {
    completionItems.set(symbol.name, toCompletionItem(symbol));
  }

  const currentFilePath = uriToFilePath(document.uri);
  if (currentFilePath) {
    const imported = await collectImportedTopLevelSymbols(index, currentFilePath);
    for (const symbol of imported) {
      if (!completionItems.has(symbol.name)) {
        completionItems.set(symbol.name, toCompletionItem(symbol));
      }
    }
  }

  return Array.from(completionItems.values());
});

connection.onHover(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return null;
  }
  const token = getIdentifierToken(document, params.position);
  if (!token) {
    return null;
  }
  if (isInsideCommentOrString(document.getText(), token.startOffset)) {
    return null;
  }

  const index = getOrCreateSymbolIndex(document);
  const symbol = await resolveSymbolForHover(document, index, token.text, token.startOffset);
  if (!symbol) {
    return null;
  }
  return {
    range: token.range,
    contents: buildHoverContents(symbol),
  };
});

connection.onSignatureHelp(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return null;
  }
  const source = document.getText();
  const offset = document.offsetAt(params.position);
  if (isInsideCommentOrString(source, offset)) {
    return null;
  }

  const activeCall = findActiveCall(source, offset);
  if (!activeCall) {
    return null;
  }

  const index = getOrCreateSymbolIndex(document);
  const callable = await resolveCallable(document, index, activeCall.name);
  if (!callable) {
    return null;
  }

  const parameters = callable.params.map((item) => ({
    label: `${item.name}: ${item.type}`,
  }));
  return {
    signatures: [
      {
        label: callable.label,
        documentation: callable.documentation
          ? { kind: MarkupKind.Markdown, value: callable.documentation }
          : undefined,
        parameters,
      },
    ],
    activeSignature: 0,
    activeParameter: Math.min(activeCall.activeParameter, Math.max(parameters.length - 1, 0)),
  };
});

connection.onDefinition(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return null;
  }
  const token = getIdentifierToken(document, params.position);
  if (!token) {
    return null;
  }
  if (isInsideCommentOrString(document.getText(), token.startOffset)) {
    return null;
  }

  const index = getOrCreateSymbolIndex(document);
  const locations = await resolveDefinitionLocations(document, index, token.text, token.startOffset);
  if (locations.length === 0) {
    return null;
  }
  return locations.length === 1 ? locations[0] : locations;
});

documents.listen(connection);
connection.listen();

function normalizeSettings(input) {
  const command = typeof input.command === "string" ? input.command.trim() : "midori";
  const args = Array.isArray(input.args) ? input.args.filter((x) => typeof x === "string") : [];
  const runOnType = typeof input.runOnType === "boolean" ? input.runOnType : true;
  const debounceMsRaw = typeof input.debounceMs === "number" ? input.debounceMs : 250;
  const debounceMs = Math.max(50, Math.floor(debounceMsRaw));
  const workspaceRoot =
    typeof input.workspaceRoot === "string" && input.workspaceRoot.trim().length > 0
      ? input.workspaceRoot
      : process.cwd();
  return {
    command: command || "midori",
    args,
    runOnType,
    debounceMs,
    workspaceRoot,
  };
}

function scheduleValidation(document, immediate) {
  const delay = immediate ? 0 : settings.debounceMs;
  clearTimer(document.uri);
  const timer = setTimeout(() => {
    void validateDocument(document);
  }, delay);
  timers.set(document.uri, timer);
}

function clearTimer(uri) {
  const timer = timers.get(uri);
  if (timer) {
    clearTimeout(timer);
    timers.delete(uri);
  }
}

async function validateDocument(document) {
  const token = (versions.get(document.uri) || 0) + 1;
  versions.set(document.uri, token);
  clearTimer(document.uri);

  try {
    const diagnostics = await runCheck(document);
    const current = documents.get(document.uri);
    const isStale = !current || versions.get(document.uri) !== token || current.version !== document.version;
    if (!isStale) {
      connection.sendDiagnostics({ uri: document.uri, diagnostics });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const current = documents.get(document.uri);
    if (!current || versions.get(document.uri) !== token) {
      return;
    }
    connection.sendDiagnostics({
      uri: document.uri,
      diagnostics: [
        {
          range: {
            start: { line: 0, character: 0 },
            end: { line: 0, character: 1 },
          },
          severity: DiagnosticSeverity.Error,
          source: "midori-lsp",
          code: "MD9000",
          message,
        },
      ],
    });
  }
}

async function runCheck(document) {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "midori-lsp-"));
  const tempFile = path.join(tempDir, "document.mdr");
  await fs.writeFile(tempFile, document.getText(), "utf8");

  try {
    const output = await execMidoriCheck(tempFile);
    return parseDiagnostics(output);
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
  }
}

function execMidoriCheck(tempFile) {
  const args = [...settings.args, "check", tempFile];
  return new Promise((resolve, reject) => {
    const proc = spawn(settings.command, args, {
      cwd: settings.workspaceRoot,
      windowsHide: true,
      shell: process.platform === "win32",
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", (err) => {
      reject(
        new Error(
          `Failed to run MIDORI diagnostics command '${settings.command}'. ${err.message}. Configure 'midori.lsp.command' and 'midori.lsp.args'.`,
        ),
      );
    });
    proc.on("close", () => {
      resolve(`${stdout}\n${stderr}`);
    });
  });
}

function parseDiagnostics(output) {
  const diagnostics = [];
  const lines = output.split(/\r?\n/);
  let last = null;

  for (const line of lines) {
    const match = line.match(
      /^(.+):(\d+):(\d+):\s(error|warning)(?:\[(MD\d{4})\])?:\s(.*)$/,
    );
    if (match) {
      const lineNum = Math.max(0, Number(match[2]) - 1);
      const colNum = Math.max(0, Number(match[3]) - 1);
      const severity =
        match[4] === "warning" ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error;
      const diagnostic = {
        range: {
          start: { line: lineNum, character: colNum },
          end: { line: lineNum, character: colNum + 1 },
        },
        severity,
        source: "midori",
        code: match[5] || undefined,
        message: match[6],
      };
      diagnostics.push(diagnostic);
      last = diagnostic;
      continue;
    }

    const hint = line.match(/^\s*hint:\s*(.*)$/);
    if (hint && last) {
      last.message += `\nHint: ${hint[1]}`;
    }
  }

  return diagnostics;
}

/**
 * @param {TextDocument} document
 * @returns {SymbolIndex}
 */
function getOrCreateSymbolIndex(document) {
  const cached = symbolCache.get(document.uri);
  if (cached && cached.version === document.version) {
    return cached.index;
  }
  const index = buildSymbolIndex(document);
  symbolCache.set(document.uri, {
    version: document.version,
    index,
  });
  return index;
}

/**
 * @param {TextDocument} document
 * @returns {SymbolIndex}
 */
function buildSymbolIndex(document) {
  const source = document.getText();
  /** @type {SymbolIndex} */
  const index = {
    uri: document.uri,
    imports: [],
    functions: [],
    enums: [],
    variants: [],
    errors: [],
    params: [],
    locals: [],
    topLevelSymbols: [],
    allSymbols: [],
  };

  const importRe = /\bimport\s+"([^"]+)"/g;
  for (const match of source.matchAll(importRe)) {
    const importPath = match[1];
    if (!importPath) {
      continue;
    }
    const importPathOffset = match.index + match[0].indexOf(importPath);
    index.imports.push({ path: importPath, offset: importPathOffset });
  }

  const errorRe = /\berror\s+([A-Za-z_][A-Za-z0-9_]*)/g;
  for (const match of source.matchAll(errorRe)) {
    const errorName = match[1];
    if (!errorName) {
      continue;
    }
    const nameOffset = match.index + match[0].indexOf(errorName);
    index.errors.push(
      createSymbol(document, {
        name: errorName,
        kind: "error",
        offset: nameOffset,
      }),
    );
  }

  const enumRe = /\benum\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{/g;
  for (const match of source.matchAll(enumRe)) {
    const enumName = match[1];
    if (!enumName) {
      continue;
    }
    const enumNameOffset = match.index + match[0].indexOf(enumName);
    const openBraceOffset = match.index + match[0].lastIndexOf("{");
    const closeBraceOffset = findMatchingBrace(source, openBraceOffset);
    index.enums.push(
      createSymbol(document, {
        name: enumName,
        kind: "enum",
        offset: enumNameOffset,
      }),
    );
    if (closeBraceOffset < 0) {
      continue;
    }

    const bodyText = source.slice(openBraceOffset + 1, closeBraceOffset);
    const bodyOffset = openBraceOffset + 1;
    const variantRe = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s*(?:,)?\s*$/gm;
    for (const variantMatch of bodyText.matchAll(variantRe)) {
      const variantName = variantMatch[1];
      if (!variantName) {
        continue;
      }
      const variantParams = parseParameterList(variantMatch[2] || "");
      const variantOffset = bodyOffset + variantMatch.index + variantMatch[0].indexOf(variantName);
      const signature = `${variantName}(${formatCallableParams(variantParams)})`;
      index.variants.push(
        createSymbol(document, {
          name: variantName,
          kind: "variant",
          container: enumName,
          offset: variantOffset,
          params: variantParams,
          signature,
          returnType: enumName,
        }),
      );
    }
  }

  const externRanges = [];
  const externFnRe =
    /\bextern(?:\s+"[^"]*")?\s+fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*])?\s*\(([\s\S]*?)\)\s*(?:->\s*([^\n{]+))?/g;
  for (const match of source.matchAll(externFnRe)) {
    const fnName = match[1];
    if (!fnName) {
      continue;
    }
    const params = parseParameterList(match[2] || "");
    const returnType = normalizeTypeName(match[3] || "Void");
    const fnNameOffset = match.index + match[0].indexOf(fnName);
    const signature = `${fnName}(${formatCallableParams(params)}) -> ${returnType}`;
    index.functions.push(
      createSymbol(document, {
        name: fnName,
        kind: "function",
        offset: fnNameOffset,
        params,
        signature,
        returnType,
        isExtern: true,
      }),
    );
    externRanges.push({
      start: match.index,
      end: match.index + match[0].length,
    });
  }

  const fnRe =
    /\b(?:pub\s+)?(?:task\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*])?\s*\(([\s\S]*?)\)\s*(?:->\s*([^{\n]+))?\s*\{/g;
  for (const match of source.matchAll(fnRe)) {
    if (isInsideRanges(match.index, externRanges)) {
      continue;
    }
    const fnName = match[1];
    if (!fnName) {
      continue;
    }
    const params = parseParameterList(match[2] || "");
    const returnType = normalizeTypeName(match[3] || "Void");
    const fnNameOffset = match.index + match[0].indexOf(fnName);
    const openBraceOffset = match.index + match[0].lastIndexOf("{");
    const closeBraceOffset = findMatchingBrace(source, openBraceOffset);
    const signature = `${fnName}(${formatCallableParams(params)}) -> ${returnType}`;

    const functionSymbol = createSymbol(document, {
      name: fnName,
      kind: "function",
      offset: fnNameOffset,
      params,
      signature,
      returnType,
      isExtern: false,
      bodyStartOffset: openBraceOffset + 1,
      bodyEndOffset: closeBraceOffset >= 0 ? closeBraceOffset : undefined,
    });
    index.functions.push(functionSymbol);

    const paramsStartOffset = match.index + match[0].indexOf("(") + 1;
    const paramSegments = splitTopLevelSegments(match[2] || "");
    const parsedParams = parseParameterList(match[2] || "");
    for (let i = 0; i < parsedParams.length; i += 1) {
      const param = parsedParams[i];
      const segment = paramSegments[i];
      if (!segment) {
        continue;
      }
      const rel = segment.text.indexOf(param.name);
      if (rel < 0) {
        continue;
      }
      const paramOffset = paramsStartOffset + segment.start + rel;
      index.params.push(
        createSymbol(document, {
          name: param.name,
          kind: "param",
          container: fnName,
          type: param.type,
          offset: paramOffset,
        }),
      );
    }

    if (closeBraceOffset < 0) {
      continue;
    }
    const bodyText = source.slice(openBraceOffset + 1, closeBraceOffset);
    const bodyBaseOffset = openBraceOffset + 1;
    const localRe = /\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([^=:\n]+))?\s*(?::=|=)/g;
    for (const localMatch of bodyText.matchAll(localRe)) {
      const localName = localMatch[1];
      if (!localName) {
        continue;
      }
      const localType = normalizeTypeName(localMatch[2] || "");
      const localOffset = bodyBaseOffset + localMatch.index + localMatch[0].indexOf(localName);
      index.locals.push(
        createSymbol(document, {
          name: localName,
          kind: "local",
          container: fnName,
          type: localType || undefined,
          offset: localOffset,
        }),
      );
    }
  }

  index.topLevelSymbols = [...index.functions, ...index.enums, ...index.variants, ...index.errors];
  index.allSymbols = [...index.topLevelSymbols, ...index.params, ...index.locals];
  return index;
}

/**
 * @param {TextDocument} document
 * @param {{name: string, kind: SymbolKindTag, offset: number} & Record<string, unknown>} input
 * @returns {MidoriSymbol}
 */
function createSymbol(document, input) {
  const start = document.positionAt(input.offset);
  const end = document.positionAt(input.offset + input.name.length);
  return {
    ...input,
    uri: document.uri,
    range: { start, end },
  };
}

/**
 * @param {SymbolIndex} index
 * @param {number} offset
 * @returns {MidoriSymbol[]}
 */
function getSymbolsInScope(index, offset) {
  const inScope = [...index.topLevelSymbols];
  const fn = findEnclosingFunction(index, offset);
  if (!fn) {
    return inScope;
  }
  for (const param of index.params) {
    if (param.container === fn.name) {
      inScope.push(param);
    }
  }
  for (const local of index.locals) {
    if (local.container === fn.name && local.offset <= offset) {
      inScope.push(local);
    }
  }
  return inScope;
}

/**
 * @param {SymbolIndex} index
 * @param {number} offset
 * @returns {MidoriSymbol | null}
 */
function findEnclosingFunction(index, offset) {
  let current = null;
  for (const fn of index.functions) {
    if (
      typeof fn.bodyStartOffset === "number"
      && typeof fn.bodyEndOffset === "number"
      && offset >= fn.bodyStartOffset
      && offset <= fn.bodyEndOffset
    ) {
      if (
        !current
        || current.bodyEndOffset - current.bodyStartOffset > fn.bodyEndOffset - fn.bodyStartOffset
      ) {
        current = fn;
      }
    }
  }
  return current;
}

/**
 * @param {MidoriSymbol} symbol
 * @returns {import("vscode-languageserver").CompletionItem}
 */
function toCompletionItem(symbol) {
  if (symbol.kind === "function") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Function,
      detail: symbol.signature || symbol.name,
      insertText: buildCallSnippet(symbol.name, symbol.params || []),
      insertTextFormat: InsertTextFormat.Snippet,
    };
  }
  if (symbol.kind === "variant") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.EnumMember,
      detail: symbol.container ? `${symbol.container} variant` : "enum variant",
      insertText: buildCallSnippet(symbol.name, symbol.params || []),
      insertTextFormat: InsertTextFormat.Snippet,
    };
  }
  if (symbol.kind === "enum") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Enum,
      detail: "enum",
    };
  }
  if (symbol.kind === "error") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Class,
      detail: "custom error",
    };
  }
  return {
    label: symbol.name,
    kind: CompletionItemKind.Variable,
    detail: symbol.type ? `${symbol.kind}: ${symbol.type}` : symbol.kind,
  };
}

/**
 * @typedef {{
 *   name: string,
 *   params: Array<{name: string, type: string}>,
 *   returnType: string,
 *   documentation?: string,
 * }} BuiltinCallable
 */

/**
 * @param {TextDocument} document
 * @param {SymbolIndex} index
 * @param {string} name
 * @param {number} offset
 * @returns {Promise<MidoriSymbol | BuiltinCallable | null>}
 */
async function resolveSymbolForHover(document, index, name, offset) {
  const local = findBestLocalSymbol(index, name, offset);
  if (local) {
    return local;
  }
  const localTopLevel = index.topLevelSymbols.find((symbol) => symbol.name === name);
  if (localTopLevel) {
    return localTopLevel;
  }
  const currentFilePath = uriToFilePath(document.uri);
  if (currentFilePath) {
    const imported = await collectImportedTopLevelSymbols(index, currentFilePath);
    const importedSymbol = imported.find((symbol) => symbol.name === name);
    if (importedSymbol) {
      return importedSymbol;
    }
  }
  return BUILTIN_FUNCTION_MAP.get(name) || null;
}

/**
 * @param {MidoriSymbol | BuiltinCallable} symbol
 * @returns {{kind: string, value: string}}
 */
function buildHoverContents(symbol) {
  if ("kind" in symbol) {
    if (symbol.kind === "function") {
      const label = symbol.signature || `${symbol.name}() -> ${symbol.returnType || "Void"}`;
      const externNote = symbol.isExtern ? "\nExtern declaration." : "";
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nfn ${label}\n\`\`\`${externNote}`,
      };
    }
    if (symbol.kind === "variant") {
      const variantSig = symbol.signature || `${symbol.name}()`;
      const detail = symbol.container ? `\nEnum: \`${symbol.container}\`` : "";
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\n${variantSig}\n\`\`\`${detail}`,
      };
    }
    if (symbol.kind === "enum") {
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nenum ${symbol.name}\n\`\`\``,
      };
    }
    if (symbol.kind === "error") {
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nerror ${symbol.name}\n\`\`\``,
      };
    }
    return {
      kind: MarkupKind.Markdown,
      value: symbol.type ? `\`${symbol.name}: ${symbol.type}\`` : `\`${symbol.name}\``,
    };
  }

  return {
    kind: MarkupKind.Markdown,
    value: `\`\`\`midori\n${symbol.name}(${formatCallableParams(symbol.params)}) -> ${symbol.returnType}\n\`\`\`\n${symbol.documentation || ""}`,
  };
}

/**
 * @param {TextDocument} document
 * @param {SymbolIndex} index
 * @param {string} name
 * @returns {Promise<{label: string, params: Array<{name: string, type: string}>, documentation?: string} | null>}
 */
async function resolveCallable(document, index, name) {
  const fn = index.functions.find((symbol) => symbol.name === name);
  if (fn) {
    return {
      label: `${fn.name}(${formatCallableParams(fn.params || [])}) -> ${fn.returnType || "Void"}`,
      params: fn.params || [],
      documentation: fn.isExtern ? "Extern function declaration." : undefined,
    };
  }

  const variant = index.variants.find((symbol) => symbol.name === name);
  if (variant) {
    return {
      label: `${variant.name}(${formatCallableParams(variant.params || [])}) -> ${variant.container || "Enum"}`,
      params: variant.params || [],
      documentation: variant.container
        ? `Variant constructor for \`${variant.container}\`.`
        : "Variant constructor.",
    };
  }

  const builtin = BUILTIN_FUNCTION_MAP.get(name);
  if (builtin) {
    return {
      label: `${builtin.name}(${formatCallableParams(builtin.params)}) -> ${builtin.returnType}`,
      params: builtin.params,
      documentation: builtin.documentation,
    };
  }

  const currentFilePath = uriToFilePath(document.uri);
  if (!currentFilePath) {
    return null;
  }
  const imported = await collectImportedTopLevelSymbols(index, currentFilePath);
  const importedFunction = imported.find(
    (symbol) => symbol.name === name && (symbol.kind === "function" || symbol.kind === "variant"),
  );
  if (!importedFunction) {
    return null;
  }
  if (importedFunction.kind === "function") {
    return {
      label: `${importedFunction.name}(${formatCallableParams(importedFunction.params || [])}) -> ${importedFunction.returnType || "Void"}`,
      params: importedFunction.params || [],
    };
  }
  return {
    label: `${importedFunction.name}(${formatCallableParams(importedFunction.params || [])}) -> ${importedFunction.container || "Enum"}`,
    params: importedFunction.params || [],
  };
}

/**
 * @param {TextDocument} document
 * @param {SymbolIndex} index
 * @param {string} name
 * @param {number} offset
 * @returns {Promise<Array<{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}>>}
 */
async function resolveDefinitionLocations(document, index, name, offset) {
  const local = findBestLocalSymbol(index, name, offset);
  if (local) {
    return [symbolToLocation(local)];
  }

  const topLevelLocal = index.topLevelSymbols.filter((symbol) => symbol.name === name);
  if (topLevelLocal.length > 0) {
    return dedupeLocations(topLevelLocal.map(symbolToLocation));
  }

  const currentFilePath = uriToFilePath(document.uri);
  if (!currentFilePath) {
    return [];
  }
  const imported = await collectImportedTopLevelSymbols(index, currentFilePath);
  const importedMatches = imported.filter((symbol) => symbol.name === name);
  return dedupeLocations(importedMatches.map(symbolToLocation));
}

/**
 * @param {SymbolIndex} index
 * @param {string} name
 * @param {number} offset
 * @returns {MidoriSymbol | null}
 */
function findBestLocalSymbol(index, name, offset) {
  const fn = findEnclosingFunction(index, offset);
  if (!fn) {
    return null;
  }
  const candidates = [];
  for (const param of index.params) {
    if (param.container === fn.name && param.name === name && param.offset <= offset) {
      candidates.push(param);
    }
  }
  for (const local of index.locals) {
    if (local.container === fn.name && local.name === name && local.offset <= offset) {
      candidates.push(local);
    }
  }
  if (candidates.length === 0) {
    return null;
  }
  candidates.sort((a, b) => b.offset - a.offset);
  return candidates[0];
}

/**
 * @param {MidoriSymbol} symbol
 * @returns {{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}}
 */
function symbolToLocation(symbol) {
  return {
    uri: symbol.uri,
    range: symbol.range,
  };
}

/**
 * @param {Array<{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}>} locations
 * @returns {Array<{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}>}
 */
function dedupeLocations(locations) {
  const seen = new Set();
  const out = [];
  for (const item of locations) {
    const key = `${item.uri}:${item.range.start.line}:${item.range.start.character}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(item);
  }
  return out;
}

/**
 * @param {SymbolIndex} index
 * @param {string} currentFilePath
 * @returns {Promise<MidoriSymbol[]>}
 */
async function collectImportedTopLevelSymbols(index, currentFilePath) {
  const collected = [];
  for (const item of index.imports) {
    const importPath = await resolveImportPath(item.path, currentFilePath);
    if (!importPath) {
      continue;
    }
    try {
      const importIndex = await getExternalSymbolIndex(importPath);
      collected.push(...importIndex.topLevelSymbols);
    } catch {
      // Ignore bad imports in IntelliSense path and keep editor responsive.
    }
  }
  return collected;
}

/**
 * @param {string} filePath
 * @returns {Promise<SymbolIndex>}
 */
async function getExternalSymbolIndex(filePath) {
  const fileUri = pathToFileURL(filePath).toString();
  const openDoc = documents.get(fileUri);
  if (openDoc) {
    return getOrCreateSymbolIndex(openDoc);
  }

  const stats = await fs.stat(filePath);
  const cached = externalIndexCache.get(filePath);
  if (cached && cached.mtimeMs === stats.mtimeMs) {
    return cached.index;
  }

  const text = await fs.readFile(filePath, "utf8");
  const doc = TextDocument.create(fileUri, "midori", 0, text);
  const index = buildSymbolIndex(doc);
  externalIndexCache.set(filePath, { mtimeMs: stats.mtimeMs, index });
  return index;
}

/**
 * @param {string} importSpec
 * @param {string} currentFilePath
 * @returns {Promise<string | null>}
 */
async function resolveImportPath(importSpec, currentFilePath) {
  const baseDir = path.dirname(currentFilePath);
  const resolvedBase = path.isAbsolute(importSpec)
    ? importSpec
    : path.resolve(baseDir, importSpec);
  const candidates = path.extname(resolvedBase)
    ? [resolvedBase]
    : [resolvedBase, `${resolvedBase}.mdr`];

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return path.normalize(candidate);
    } catch {
      // Try next candidate.
    }
  }
  return null;
}

/**
 * @param {TextDocument} document
 * @param {{line: number, character: number}} position
 * @returns {{text: string, startOffset: number, endOffset: number, range: {start: {line: number, character: number}, end: {line: number, character: number}}} | null}
 */
function getIdentifierToken(document, position) {
  const source = document.getText();
  const lineStartOffset = document.offsetAt({ line: position.line, character: 0 });
  const lineEndOffset =
    position.line + 1 < document.lineCount
      ? document.offsetAt({ line: position.line + 1, character: 0 })
      : source.length;
  const lineText = source.slice(lineStartOffset, lineEndOffset).replace(/\r?\n$/, "");

  let startChar = Math.min(position.character, lineText.length);
  let endChar = Math.min(position.character, lineText.length);

  while (startChar > 0 && isIdentChar(lineText[startChar - 1])) {
    startChar -= 1;
  }
  while (endChar < lineText.length && isIdentChar(lineText[endChar])) {
    endChar += 1;
  }

  if (startChar === endChar) {
    return null;
  }
  const text = lineText.slice(startChar, endChar);
  if (!IDENT_RE.test(text)) {
    return null;
  }
  const start = { line: position.line, character: startChar };
  const end = { line: position.line, character: endChar };
  return {
    text,
    startOffset: document.offsetAt(start),
    endOffset: document.offsetAt(end),
    range: { start, end },
  };
}

/**
 * @param {string} source
 * @param {number} offset
 * @returns {{name: string, activeParameter: number} | null}
 */
function findActiveCall(source, offset) {
  const stack = [];
  let i = 0;
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;
  let lastIdentifier = null;

  while (i < offset) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      i += 1;
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 2;
        continue;
      }
      i += 1;
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      i += 1;
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      lastIdentifier = null;
      i += 2;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      lastIdentifier = null;
      i += 2;
      continue;
    }
    if (ch === '"') {
      inString = true;
      lastIdentifier = null;
      i += 1;
      continue;
    }

    if (isIdentChar(ch)) {
      const start = i;
      i += 1;
      while (i < offset && isIdentChar(source[i])) {
        i += 1;
      }
      const text = source.slice(start, i);
      if (IDENT_RE.test(text)) {
        lastIdentifier = { text, endOffset: i };
      } else {
        lastIdentifier = null;
      }
      continue;
    }

    if (ch === "(") {
      const isCall = Boolean(lastIdentifier);
      stack.push({
        name: isCall ? lastIdentifier.text : null,
        commas: 0,
      });
      lastIdentifier = null;
      i += 1;
      continue;
    }
    if (ch === ",") {
      const top = stack[stack.length - 1];
      if (top) {
        top.commas += 1;
      }
      lastIdentifier = null;
      i += 1;
      continue;
    }
    if (ch === ")") {
      if (stack.length > 0) {
        stack.pop();
      }
      lastIdentifier = null;
      i += 1;
      continue;
    }

    if (!/\s/.test(ch)) {
      lastIdentifier = null;
    }
    i += 1;
  }

  for (let j = stack.length - 1; j >= 0; j -= 1) {
    if (stack[j].name) {
      return {
        name: stack[j].name,
        activeParameter: stack[j].commas,
      };
    }
  }
  return null;
}

/**
 * @param {string} source
 * @param {number} offset
 * @returns {boolean}
 */
function isInsideCommentOrString(source, offset) {
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = 0; i < offset; i += 1) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 1;
      }
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inString = true;
    }
  }

  return inString || inLineComment || inBlockComment;
}

/**
 * @param {string} source
 * @param {number} openBraceOffset
 * @returns {number}
 */
function findMatchingBrace(source, openBraceOffset) {
  if (source[openBraceOffset] !== "{") {
    return -1;
  }
  let depth = 0;
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = openBraceOffset; i < source.length; i += 1) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 1;
      }
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{") {
      depth += 1;
      continue;
    }
    if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return i;
      }
    }
  }
  return -1;
}

/**
 * @param {string} text
 * @returns {Array<{name: string, type: string}>}
 */
function parseParameterList(text) {
  const params = [];
  for (const segment of splitTopLevelSegments(text)) {
    const colonIndex = findTopLevelChar(segment.text, ":");
    if (colonIndex < 0) {
      continue;
    }
    const name = segment.text.slice(0, colonIndex).trim();
    const type = normalizeTypeName(segment.text.slice(colonIndex + 1));
    if (!IDENT_RE.test(name) || !type) {
      continue;
    }
    params.push({ name, type });
  }
  return params;
}

/**
 * @param {string} text
 * @returns {Array<{text: string, start: number, end: number}>}
 */
function splitTopLevelSegments(text) {
  const out = [];
  let start = 0;
  let square = 0;
  let round = 0;
  let curly = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "[") {
      square += 1;
      continue;
    }
    if (ch === "]") {
      square = Math.max(0, square - 1);
      continue;
    }
    if (ch === "(") {
      round += 1;
      continue;
    }
    if (ch === ")") {
      round = Math.max(0, round - 1);
      continue;
    }
    if (ch === "{") {
      curly += 1;
      continue;
    }
    if (ch === "}") {
      curly = Math.max(0, curly - 1);
      continue;
    }
    if (ch === "," && square === 0 && round === 0 && curly === 0) {
      pushSegment(out, text, start, i);
      start = i + 1;
    }
  }
  pushSegment(out, text, start, text.length);
  return out;
}

/**
 * @param {Array<{text: string, start: number, end: number}>} out
 * @param {string} text
 * @param {number} start
 * @param {number} end
 */
function pushSegment(out, text, start, end) {
  const raw = text.slice(start, end);
  const leftTrim = raw.length - raw.trimStart().length;
  const rightTrim = raw.length - raw.trimEnd().length;
  const trimmed = raw.trim();
  if (!trimmed) {
    return;
  }
  out.push({
    text: trimmed,
    start: start + leftTrim,
    end: end - rightTrim,
  });
}

/**
 * @param {string} text
 * @param {string} target
 * @returns {number}
 */
function findTopLevelChar(text, target) {
  let square = 0;
  let round = 0;
  let curly = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "[") {
      square += 1;
      continue;
    }
    if (ch === "]") {
      square = Math.max(0, square - 1);
      continue;
    }
    if (ch === "(") {
      round += 1;
      continue;
    }
    if (ch === ")") {
      round = Math.max(0, round - 1);
      continue;
    }
    if (ch === "{") {
      curly += 1;
      continue;
    }
    if (ch === "}") {
      curly = Math.max(0, curly - 1);
      continue;
    }
    if (ch === target && square === 0 && round === 0 && curly === 0) {
      return i;
    }
  }
  return -1;
}

/**
 * @param {string} name
 * @param {Array<{name: string, type: string}>} params
 * @returns {string}
 */
function buildCallSnippet(name, params) {
  if (!params || params.length === 0) {
    return `${name}()`;
  }
  const placeholders = params.map(
    (item, i) => "\\${" + String(i + 1) + ":" + item.name + "}",
  );
  return `${name}(${placeholders.join(", ")})`;
}

/**
 * @param {Array<{name: string, type: string}>} params
 * @returns {string}
 */
function formatCallableParams(params) {
  if (!params || params.length === 0) {
    return "";
  }
  return params.map((item) => `${item.name}: ${item.type}`).join(", ");
}

/**
 * @param {string} text
 * @returns {string}
 */
function normalizeTypeName(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

/**
 * @param {number} start
 * @param {Array<{start: number, end: number}>} ranges
 * @returns {boolean}
 */
function isInsideRanges(start, ranges) {
  for (const item of ranges) {
    if (start >= item.start && start <= item.end) {
      return true;
    }
  }
  return false;
}

/**
 * @param {string} uri
 * @returns {string | null}
 */
function uriToFilePath(uri) {
  if (!uri.startsWith("file://")) {
    return null;
  }
  try {
    return fileURLToPath(uri);
  } catch {
    return null;
  }
}

/**
 * @param {string} ch
 * @returns {boolean}
 */
function isIdentChar(ch) {
  return /[A-Za-z0-9_]/.test(ch);
}
