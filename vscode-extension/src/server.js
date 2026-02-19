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
  SymbolKind,
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
  diagnosticsTimeoutMs: 15000,
  diagnosticsMaxOutputBytes: 256 * 1024,
  diagnosticsMaxCount: 250,
  maxDocumentBytes: 2 * 1024 * 1024,
  maxWorkspaceFiles: 1500,
  maxExternalIndexEntries: 750,
  allowExternalImports: false,
};

/** @type {Map<string, NodeJS.Timeout>} */
const timers = new Map();
/** @type {Map<string, number>} */
const versions = new Map();
/** @type {Map<string, {version: number, index: SymbolIndex}>} */
const symbolCache = new Map();
/** @type {Map<string, {mtimeMs: number, index: SymbolIndex}>} */
const externalIndexCache = new Map();
/** @type {Map<string, import("node:child_process").ChildProcess>} */
const runningChecks = new Map();

const WORKSPACE_FILES_CACHE_TTL_MS = 4000;
const MAX_WORKSPACE_SYMBOL_RESULTS = 250;
const MAX_REFERENCE_RESULTS = 750;
const IGNORED_WORKSPACE_DIRS = new Set([
  ".git",
  ".hg",
  ".svn",
  ".idea",
  ".vscode",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache",
  ".mypy_cache",
  ".venv",
  "venv",
  "node_modules",
  "dist",
  "build",
  "output",
]);

let workspaceFileCache = {
  root: "",
  expiresAt: 0,
  files: [],
};

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
  trimExternalIndexCache();
  invalidateWorkspaceFileCache();
  return {
    capabilities: {
      textDocumentSync: TextDocumentSyncKind.Incremental,
      completionProvider: {
        triggerCharacters: [":", "(", '"', "/"],
      },
      hoverProvider: true,
      signatureHelpProvider: {
        triggerCharacters: ["(", ","],
        retriggerCharacters: [","],
      },
      definitionProvider: true,
      referencesProvider: true,
      renameProvider: {
        prepareProvider: true,
      },
      documentSymbolProvider: true,
      workspaceSymbolProvider: true,
    },
  };
});

documents.onDidOpen((event) => {
  symbolCache.delete(event.document.uri);
  invalidateWorkspaceFileCache();
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
  invalidateWorkspaceFileCache();
  scheduleValidation(event.document, true);
});

documents.onDidClose((event) => {
  clearTimer(event.document.uri);
  symbolCache.delete(event.document.uri);
  cancelRunningCheck(event.document.uri);
  connection.sendDiagnostics({ uri: event.document.uri, diagnostics: [] });
});

connection.onCompletion(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return [];
  }
  const source = document.getText();
  const offset = document.offsetAt(params.position);
  const importContext = getImportCompletionContext(document, params.position);
  if (importContext) {
    return provideImportPathCompletions(document, importContext);
  }
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

connection.onReferences(async (params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return [];
  }
  const token = getIdentifierToken(document, params.position);
  if (!token) {
    return [];
  }
  if (isInsideCommentOrString(document.getText(), token.startOffset)) {
    return [];
  }

  const index = getOrCreateSymbolIndex(document);
  const target = await resolveRenameTarget(document, index, token.text, token.startOffset);
  if (!target) {
    return [];
  }
  return findReferenceLocations(target, token.text, {
    includeDeclaration: params.context.includeDeclaration,
  });
});

connection.onPrepareRename(async (params) => {
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
  if (KEYWORDS.includes(token.text) || BUILTIN_FUNCTION_MAP.has(token.text)) {
    return null;
  }

  const index = getOrCreateSymbolIndex(document);
  const target = await resolveRenameTarget(document, index, token.text, token.startOffset);
  if (!target) {
    return null;
  }
  return {
    range: token.range,
    placeholder: token.text,
  };
});

connection.onRenameRequest(async (params) => {
  const newName = (params.newName || "").trim();
  if (!IDENT_RE.test(newName) || KEYWORDS.includes(newName)) {
    return {
      changes: {},
    };
  }

  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return {
      changes: {},
    };
  }
  const token = getIdentifierToken(document, params.position);
  if (!token) {
    return {
      changes: {},
    };
  }
  if (isInsideCommentOrString(document.getText(), token.startOffset)) {
    return {
      changes: {},
    };
  }

  const index = getOrCreateSymbolIndex(document);
  const target = await resolveRenameTarget(document, index, token.text, token.startOffset);
  if (!target) {
    return {
      changes: {},
    };
  }

  const references = await findReferenceLocations(target, token.text, {
    includeDeclaration: true,
  });
  return buildWorkspaceEditForRename(references, newName);
});

connection.onDocumentSymbol((params) => {
  const document = documents.get(params.textDocument.uri);
  if (!document) {
    return [];
  }
  const index = getOrCreateSymbolIndex(document);
  return buildDocumentSymbols(document, index);
});

connection.onWorkspaceSymbol(async (params) => {
  return queryWorkspaceSymbols(params.query || "");
});

documents.listen(connection);
connection.listen();

function normalizeSettings(input) {
  const command = typeof input.command === "string" ? input.command.trim() : "midori";
  const args = Array.isArray(input.args) ? input.args.filter((x) => typeof x === "string") : [];
  const runOnType = typeof input.runOnType === "boolean" ? input.runOnType : true;
  const debounceMsRaw = typeof input.debounceMs === "number" ? input.debounceMs : 250;
  const debounceMs = Math.max(50, Math.floor(debounceMsRaw));
  const diagnosticsTimeoutMsRaw =
    typeof input.diagnosticsTimeoutMs === "number" ? input.diagnosticsTimeoutMs : 15000;
  const diagnosticsTimeoutMs = clampNumber(diagnosticsTimeoutMsRaw, 2000, 120000, 15000);
  const diagnosticsMaxOutputBytesRaw =
    typeof input.diagnosticsMaxOutputBytes === "number"
      ? input.diagnosticsMaxOutputBytes
      : 256 * 1024;
  const diagnosticsMaxOutputBytes = clampNumber(
    diagnosticsMaxOutputBytesRaw,
    64 * 1024,
    2 * 1024 * 1024,
    256 * 1024,
  );
  const diagnosticsMaxCountRaw =
    typeof input.diagnosticsMaxCount === "number" ? input.diagnosticsMaxCount : 250;
  const diagnosticsMaxCount = clampNumber(diagnosticsMaxCountRaw, 1, 1000, 250);
  const maxDocumentBytesRaw =
    typeof input.maxDocumentBytes === "number" ? input.maxDocumentBytes : 2 * 1024 * 1024;
  const maxDocumentBytes = clampNumber(maxDocumentBytesRaw, 64 * 1024, 5 * 1024 * 1024, 2 * 1024 * 1024);
  const maxWorkspaceFilesRaw =
    typeof input.maxWorkspaceFiles === "number" ? input.maxWorkspaceFiles : 1500;
  const maxWorkspaceFiles = clampNumber(maxWorkspaceFilesRaw, 100, 15000, 1500);
  const maxExternalIndexEntriesRaw =
    typeof input.maxExternalIndexEntries === "number" ? input.maxExternalIndexEntries : 750;
  const maxExternalIndexEntries = clampNumber(maxExternalIndexEntriesRaw, 100, 5000, 750);
  const allowExternalImports = Boolean(input.allowExternalImports);
  const workspaceRootRaw =
    typeof input.workspaceRoot === "string" && input.workspaceRoot.trim().length > 0
      ? input.workspaceRoot
      : process.cwd();
  const workspaceRoot = path.resolve(workspaceRootRaw);
  return {
    command: command || "midori",
    args,
    runOnType,
    debounceMs,
    workspaceRoot,
    diagnosticsTimeoutMs,
    diagnosticsMaxOutputBytes,
    diagnosticsMaxCount,
    maxDocumentBytes,
    maxWorkspaceFiles,
    maxExternalIndexEntries,
    allowExternalImports,
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
  cancelRunningCheck(document.uri);

  try {
    const diagnostics = await runCheck(document, token);
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

async function runCheck(document, token) {
  const sizeBytes = Buffer.byteLength(document.getText(), "utf8");
  if (sizeBytes > settings.maxDocumentBytes) {
    return [
      {
        range: {
          start: { line: 0, character: 0 },
          end: { line: 0, character: 1 },
        },
        severity: DiagnosticSeverity.Warning,
        source: "midori-lsp",
        code: "MD9001",
        message:
          `File too large for live diagnostics (${sizeBytes} bytes > ${settings.maxDocumentBytes}). `
          + "Use 'midori check <file>' from terminal for full validation.",
      },
    ];
  }

  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "midori-lsp-"));
  const tempFile = path.join(tempDir, "document.mdr");
  await fs.writeFile(tempFile, document.getText(), "utf8");

  try {
    const output = await execMidoriCheck(tempFile, document.uri, token);
    return parseDiagnostics(output).slice(0, settings.diagnosticsMaxCount);
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
  }
}

function execMidoriCheck(tempFile, uri, token) {
  const args = [...settings.args, "check", tempFile];
  return new Promise((resolve, reject) => {
    const proc = spawn(settings.command, args, {
      cwd: settings.workspaceRoot,
      windowsHide: true,
      shell: false,
    });
    runningChecks.set(uri, proc);
    let stdout = "";
    let stderr = "";
    let totalBytes = 0;
    let truncated = false;
    let timedOut = false;
    const onChunk = (chunk, sink) => {
      if (versions.get(uri) !== token) {
        return;
      }
      const value = chunk.toString();
      const chunkSize = Buffer.byteLength(value, "utf8");
      const remaining = settings.diagnosticsMaxOutputBytes - totalBytes;
      if (remaining <= 0) {
        truncated = true;
        return;
      }
      if (chunkSize <= remaining) {
        if (sink === "stdout") {
          stdout += value;
        } else {
          stderr += value;
        }
        totalBytes += chunkSize;
        return;
      }
      const kept = value.slice(0, remaining);
      if (sink === "stdout") {
        stdout += kept;
      } else {
        stderr += kept;
      }
      totalBytes += Buffer.byteLength(kept, "utf8");
      truncated = true;
    };
    const timeout = setTimeout(() => {
      timedOut = true;
      try {
        proc.kill();
      } catch {
        // Ignore process kill failures.
      }
    }, settings.diagnosticsTimeoutMs);

    proc.stdout.on("data", (chunk) => {
      onChunk(chunk, "stdout");
    });
    proc.stderr.on("data", (chunk) => {
      onChunk(chunk, "stderr");
    });
    proc.on("error", (err) => {
      clearTimeout(timeout);
      if (runningChecks.get(uri) === proc) {
        runningChecks.delete(uri);
      }
      reject(
        new Error(
          `Failed to run MIDORI diagnostics command '${settings.command}'. ${err.message}. Configure 'midori.lsp.command' and 'midori.lsp.args'.`,
        ),
      );
    });
    proc.on("close", () => {
      clearTimeout(timeout);
      if (runningChecks.get(uri) === proc) {
        runningChecks.delete(uri);
      }
      if (timedOut) {
        reject(
          new Error(
            `MIDORI diagnostics timed out after ${settings.diagnosticsTimeoutMs} ms. Increase 'midori.diagnostics.timeoutMs' or run 'midori check' manually.`,
          ),
        );
        return;
      }
      const suffix = truncated
        ? "\n[midori-lsp] Diagnostic output truncated to configured byte limit."
        : "";
      resolve(`${stdout}\n${stderr}${suffix}`);
    });
  });
}

function parseDiagnostics(output) {
  const diagnostics = [];
  const lines = output.split(/\r?\n/);
  let last = null;

  for (const line of lines) {
    if (!line || line.length > 5000) {
      continue;
    }
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
      if (diagnostics.length >= settings.diagnosticsMaxCount) {
        break;
      }
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
 * @param {TextDocument} document
 * @param {{line: number, character: number}} position
 * @returns {{typedPath: string} | null}
 */
function getImportCompletionContext(document, position) {
  const source = document.getText();
  const lineStartOffset = document.offsetAt({ line: position.line, character: 0 });
  const offset = document.offsetAt(position);
  const linePrefix = source.slice(lineStartOffset, offset);
  const match = linePrefix.match(/\bimport\s+"([^"]*)$/);
  if (!match) {
    return null;
  }
  return {
    typedPath: match[1].replace(/\\/g, "/"),
  };
}

/**
 * @param {TextDocument} document
 * @param {{typedPath: string}} context
 * @returns {Promise<import("vscode-languageserver").CompletionItem[]>}
 */
async function provideImportPathCompletions(document, context) {
  const currentFilePath = uriToFilePath(document.uri);
  if (!currentFilePath) {
    return [];
  }
  const typedPath = context.typedPath;
  const slash = typedPath.lastIndexOf("/");
  const dirPrefix = slash >= 0 ? typedPath.slice(0, slash + 1) : "";
  const namePrefix = slash >= 0 ? typedPath.slice(slash + 1) : typedPath;
  const lookupDir = path.resolve(path.dirname(currentFilePath), dirPrefix || ".");

  if (!settings.allowExternalImports && !isPathWithinRoot(lookupDir, settings.workspaceRoot)) {
    return [];
  }

  let entries = [];
  try {
    entries = await fs.readdir(lookupDir, { withFileTypes: true });
  } catch {
    return [];
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));

  const items = [];
  const seen = new Set();
  for (const entry of entries) {
    if (entry.name.startsWith(".") || !entry.name.startsWith(namePrefix)) {
      continue;
    }
    if (entry.isDirectory()) {
      const label = `${dirPrefix}${entry.name}/`;
      if (seen.has(label)) {
        continue;
      }
      seen.add(label);
      items.push({
        label,
        kind: CompletionItemKind.Folder,
        detail: "MIDORI module folder",
        insertText: label,
      });
      continue;
    }
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".mdr")) {
      continue;
    }
    const base = entry.name.slice(0, -4);
    const label = `${dirPrefix}${base}`;
    if (seen.has(label)) {
      continue;
    }
    seen.add(label);
    items.push({
      label,
      kind: CompletionItemKind.File,
      detail: "MIDORI module",
      insertText: label,
    });
  }
  return items;
}

/**
 * @param {TextDocument} document
 * @param {SymbolIndex} index
 * @returns {import("vscode-languageserver").DocumentSymbol[]}
 */
function buildDocumentSymbols(document, index) {
  /** @type {import("vscode-languageserver").DocumentSymbol[]} */
  const symbols = [];

  const functions = [...index.functions].sort((a, b) => a.offset - b.offset);
  for (const fn of functions) {
    const start = document.positionAt(fn.offset);
    const end =
      typeof fn.bodyEndOffset === "number"
        ? document.positionAt(fn.bodyEndOffset + 1)
        : fn.range.end;
    const fnSymbol = {
      name: fn.name,
      detail: fn.signature || undefined,
      kind: SymbolKind.Function,
      range: { start, end },
      selectionRange: fn.range,
      children: [],
    };
    const params = index.params
      .filter((item) => item.container === fn.name)
      .sort((a, b) => a.offset - b.offset);
    for (const param of params) {
      fnSymbol.children.push({
        name: param.name,
        detail: param.type || undefined,
        kind: SymbolKind.Variable,
        range: param.range,
        selectionRange: param.range,
      });
    }
    const locals = index.locals
      .filter((item) => item.container === fn.name)
      .sort((a, b) => a.offset - b.offset);
    for (const local of locals) {
      fnSymbol.children.push({
        name: local.name,
        detail: local.type || undefined,
        kind: SymbolKind.Variable,
        range: local.range,
        selectionRange: local.range,
      });
    }
    symbols.push(fnSymbol);
  }

  const enums = [...index.enums].sort((a, b) => a.offset - b.offset);
  for (const item of enums) {
    const enumSymbol = {
      name: item.name,
      kind: SymbolKind.Enum,
      range: item.range,
      selectionRange: item.range,
      children: [],
    };
    const variants = index.variants
      .filter((variant) => variant.container === item.name)
      .sort((a, b) => a.offset - b.offset);
    for (const variant of variants) {
      enumSymbol.children.push({
        name: variant.name,
        detail: variant.signature || undefined,
        kind: SymbolKind.EnumMember,
        range: variant.range,
        selectionRange: variant.range,
      });
    }
    symbols.push(enumSymbol);
  }

  const errors = [...index.errors].sort((a, b) => a.offset - b.offset);
  for (const item of errors) {
    symbols.push({
      name: item.name,
      kind: SymbolKind.Class,
      range: item.range,
      selectionRange: item.range,
    });
  }

  return symbols.sort((a, b) => {
    if (a.range.start.line !== b.range.start.line) {
      return a.range.start.line - b.range.start.line;
    }
    return a.range.start.character - b.range.start.character;
  });
}

/**
 * @param {string} query
 * @returns {Promise<import("vscode-languageserver").SymbolInformation[]>}
 */
async function queryWorkspaceSymbols(query) {
  const normalizedQuery = query.trim().toLowerCase();
  const files = await getWorkspaceMidoriFiles();
  /** @type {import("vscode-languageserver").SymbolInformation[]} */
  const results = [];

  for (const filePath of files) {
    const uri = pathToFileURL(filePath).toString();
    const context = await getDocumentContextByUri(uri);
    if (!context) {
      continue;
    }
    for (const symbol of context.index.topLevelSymbols) {
      if (normalizedQuery && !symbol.name.toLowerCase().includes(normalizedQuery)) {
        continue;
      }
      results.push({
        name: symbol.name,
        kind: toLspSymbolKind(symbol.kind),
        location: symbolToLocation(symbol),
        containerName: symbol.container || undefined,
      });
      if (results.length >= MAX_WORKSPACE_SYMBOL_RESULTS) {
        return results;
      }
    }
  }
  return results;
}

/**
 * @param {TextDocument} document
 * @param {SymbolIndex} index
 * @param {string} name
 * @param {number} offset
 * @returns {Promise<MidoriSymbol | null>}
 */
async function resolveRenameTarget(document, index, name, offset) {
  const symbol = await resolveSymbolForHover(document, index, name, offset);
  if (!symbol || !("kind" in symbol)) {
    return null;
  }
  return symbol;
}

/**
 * @param {MidoriSymbol} target
 * @param {string} name
 * @param {{includeDeclaration: boolean}} options
 * @returns {Promise<Array<{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}>>}
 */
async function findReferenceLocations(target, name, options) {
  if (target.kind === "local" || target.kind === "param") {
    const context = await getDocumentContextByUri(target.uri);
    if (!context) {
      return options.includeDeclaration ? [symbolToLocation(target)] : [];
    }
    const fn = context.index.functions.find((item) => item.name === target.container);
    const startOffset = fn ? fn.offset : 0;
    const endOffset =
      fn && typeof fn.bodyEndOffset === "number"
        ? fn.bodyEndOffset + 1
        : context.source.length;
    const offsets = collectIdentifierOffsets(context.source, name, startOffset, endOffset);
    const found = [];
    for (const offset of offsets) {
      if (isInsideCommentOrString(context.source, offset)) {
        continue;
      }
      const resolved = findBestLocalSymbol(context.index, name, offset);
      if (!resolved || !isSameSymbol(resolved, target)) {
        continue;
      }
      found.push(offsetToLocation(context.document, offset, name.length));
    }
    if (options.includeDeclaration) {
      found.push(symbolToLocation(target));
    }
    return dedupeLocations(found);
  }

  const targetDefinition = symbolToLocation(target);
  const candidateUris = await getReferenceCandidateUris(target);
  const out = [];
  for (const uri of candidateUris) {
    const context = await getDocumentContextByUri(uri);
    if (!context) {
      continue;
    }
    const offsets = collectIdentifierOffsets(context.source, name, 0, context.source.length);
    for (const offset of offsets) {
      if (isInsideCommentOrString(context.source, offset)) {
        continue;
      }
      const defs = await resolveDefinitionLocations(
        context.document,
        context.index,
        name,
        offset,
      );
      if (!defs.some((location) => isSameLocation(location, targetDefinition))) {
        continue;
      }
      const location = offsetToLocation(context.document, offset, name.length);
      if (!options.includeDeclaration && isSameLocation(location, targetDefinition)) {
        continue;
      }
      out.push(location);
      if (out.length >= MAX_REFERENCE_RESULTS) {
        return dedupeLocations(out);
      }
    }
  }
  if (options.includeDeclaration) {
    out.push(targetDefinition);
  }
  return dedupeLocations(out);
}

/**
 * @param {MidoriSymbol} target
 * @returns {Promise<string[]>}
 */
async function getReferenceCandidateUris(target) {
  const uris = new Set([target.uri]);
  for (const document of documents.all()) {
    if (document.languageId === "midori") {
      uris.add(document.uri);
    }
  }

  if (target.kind === "local" || target.kind === "param") {
    return Array.from(uris);
  }

  const targetPath = uriToFilePath(target.uri);
  if (!targetPath) {
    return Array.from(uris);
  }

  const files = await getWorkspaceMidoriFiles();
  for (const filePath of files) {
    if (isSamePath(filePath, targetPath)) {
      continue;
    }
    let importIndex;
    try {
      importIndex = await getExternalSymbolIndex(filePath);
    } catch {
      continue;
    }
    let importsTarget = false;
    for (const item of importIndex.imports) {
      const resolved = await resolveImportPath(item.path, filePath);
      if (resolved && isSamePath(resolved, targetPath)) {
        importsTarget = true;
        break;
      }
    }
    if (importsTarget) {
      uris.add(pathToFileURL(filePath).toString());
    }
  }
  return Array.from(uris);
}

/**
 * @param {Array<{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}>} references
 * @param {string} newName
 * @returns {{changes: Record<string, Array<{range: {start: {line: number, character: number}, end: {line: number, character: number}}, newText: string}>>}}
 */
function buildWorkspaceEditForRename(references, newName) {
  /** @type {Record<string, Array<{range: {start: {line: number, character: number}, end: {line: number, character: number}}, newText: string}>>} */
  const changes = {};
  for (const location of references) {
    if (!changes[location.uri]) {
      changes[location.uri] = [];
    }
    changes[location.uri].push({
      range: location.range,
      newText: newName,
    });
  }
  for (const uri of Object.keys(changes)) {
    changes[uri].sort((a, b) => {
      if (a.range.start.line !== b.range.start.line) {
        return b.range.start.line - a.range.start.line;
      }
      return b.range.start.character - a.range.start.character;
    });
  }
  return { changes };
}

/**
 * @param {string} uri
 * @returns {Promise<{document: TextDocument, source: string, index: SymbolIndex} | null>}
 */
async function getDocumentContextByUri(uri) {
  const open = documents.get(uri);
  if (open) {
    return {
      document: open,
      source: open.getText(),
      index: getOrCreateSymbolIndex(open),
    };
  }
  const filePath = uriToFilePath(uri);
  if (!filePath) {
    return null;
  }

  let text = "";
  let stats = null;
  try {
    [text, stats] = await Promise.all([
      fs.readFile(filePath, "utf8"),
      fs.stat(filePath),
    ]);
  } catch {
    return null;
  }
  const document = TextDocument.create(uri, "midori", 0, text);
  const cached = externalIndexCache.get(filePath);
  let index;
  if (cached && cached.mtimeMs === stats.mtimeMs) {
    touchExternalIndexCache(filePath, cached);
    index = cached.index;
  } else {
    index = buildSymbolIndex(document);
    setExternalIndexCache(filePath, { mtimeMs: stats.mtimeMs, index });
  }
  return {
    document,
    source: text,
    index,
  };
}

/**
 * @returns {Promise<string[]>}
 */
async function getWorkspaceMidoriFiles() {
  if (!settings.workspaceRoot) {
    return [];
  }
  const now = Date.now();
  if (
    workspaceFileCache.root === settings.workspaceRoot
    && workspaceFileCache.expiresAt > now
  ) {
    return workspaceFileCache.files;
  }
  const files = await scanWorkspaceMidoriFiles(settings.workspaceRoot, settings.maxWorkspaceFiles);
  workspaceFileCache = {
    root: settings.workspaceRoot,
    expiresAt: now + WORKSPACE_FILES_CACHE_TTL_MS,
    files,
  };
  return files;
}

function invalidateWorkspaceFileCache() {
  workspaceFileCache.expiresAt = 0;
}

/**
 * @param {string} root
 * @param {number} maxFiles
 * @returns {Promise<string[]>}
 */
async function scanWorkspaceMidoriFiles(root, maxFiles) {
  const normalizedRoot = path.resolve(root);
  const files = [];
  const queue = [normalizedRoot];
  while (queue.length > 0 && files.length < maxFiles) {
    const dir = queue.shift();
    if (!dir) {
      continue;
    }
    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (entry.name === "." || entry.name === "..") {
        continue;
      }
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!IGNORED_WORKSPACE_DIRS.has(entry.name)) {
          queue.push(fullPath);
        }
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      if (!entry.name.toLowerCase().endsWith(".mdr")) {
        continue;
      }
      files.push(path.normalize(fullPath));
      if (files.length >= maxFiles) {
        break;
      }
    }
  }
  return files;
}

/**
 * @param {string} source
 * @param {string} identifier
 * @param {number} startOffset
 * @param {number} endOffset
 * @returns {number[]}
 */
function collectIdentifierOffsets(source, identifier, startOffset, endOffset) {
  const out = [];
  const escaped = escapeRegExp(identifier);
  const re = new RegExp(`\\b${escaped}\\b`, "g");
  re.lastIndex = startOffset;
  while (true) {
    const match = re.exec(source);
    if (!match || typeof match.index !== "number") {
      break;
    }
    if (match.index >= endOffset) {
      break;
    }
    out.push(match.index);
  }
  return out;
}

/**
 * @param {string} value
 * @returns {string}
 */
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * @param {TextDocument} document
 * @param {number} offset
 * @param {number} length
 * @returns {{uri: string, range: {start: {line: number, character: number}, end: {line: number, character: number}}}}
 */
function offsetToLocation(document, offset, length) {
  return {
    uri: document.uri,
    range: {
      start: document.positionAt(offset),
      end: document.positionAt(offset + length),
    },
  };
}

/**
 * @param {MidoriSymbol} a
 * @param {MidoriSymbol} b
 * @returns {boolean}
 */
function isSameSymbol(a, b) {
  return (
    a.uri === b.uri
    && a.range.start.line === b.range.start.line
    && a.range.start.character === b.range.start.character
  );
}

/**
 * @param {{uri: string, range: {start: {line: number, character: number}}}} a
 * @param {{uri: string, range: {start: {line: number, character: number}}}} b
 * @returns {boolean}
 */
function isSameLocation(a, b) {
  return (
    a.uri === b.uri
    && a.range.start.line === b.range.start.line
    && a.range.start.character === b.range.start.character
  );
}

/**
 * @param {string} filePath
 * @param {{mtimeMs: number, index: SymbolIndex}} entry
 */
function touchExternalIndexCache(filePath, entry) {
  externalIndexCache.delete(filePath);
  externalIndexCache.set(filePath, entry);
}

/**
 * @param {string} filePath
 * @param {{mtimeMs: number, index: SymbolIndex}} entry
 */
function setExternalIndexCache(filePath, entry) {
  externalIndexCache.set(filePath, entry);
  trimExternalIndexCache();
}

function trimExternalIndexCache() {
  while (externalIndexCache.size > settings.maxExternalIndexEntries) {
    const oldest = externalIndexCache.keys().next().value;
    if (!oldest) {
      break;
    }
    externalIndexCache.delete(oldest);
  }
}

/**
 * @param {SymbolIndex} index
 * @param {string} currentFilePath
 * @returns {Promise<MidoriSymbol[]>}
 */
async function collectImportedTopLevelSymbols(index, currentFilePath) {
  const collected = [];
  const seenPaths = new Set();
  for (const item of index.imports) {
    const importPath = await resolveImportPath(item.path, currentFilePath);
    if (!importPath || seenPaths.has(importPath)) {
      continue;
    }
    seenPaths.add(importPath);
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
    touchExternalIndexCache(filePath, cached);
    return cached.index;
  }

  const text = await fs.readFile(filePath, "utf8");
  const doc = TextDocument.create(fileUri, "midori", 0, text);
  const index = buildSymbolIndex(doc);
  setExternalIndexCache(filePath, { mtimeMs: stats.mtimeMs, index });
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
      const normalized = path.normalize(candidate);
      if (path.extname(normalized).toLowerCase() !== ".mdr") {
        continue;
      }
      if (
        !settings.allowExternalImports
        && !isPathWithinRoot(normalized, settings.workspaceRoot)
      ) {
        continue;
      }
      return normalized;
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
 * @param {SymbolKindTag} kind
 * @returns {number}
 */
function toLspSymbolKind(kind) {
  if (kind === "function") {
    return SymbolKind.Function;
  }
  if (kind === "enum") {
    return SymbolKind.Enum;
  }
  if (kind === "variant") {
    return SymbolKind.EnumMember;
  }
  if (kind === "error") {
    return SymbolKind.Class;
  }
  return SymbolKind.Variable;
}

/**
 * @param {string} uri
 */
function cancelRunningCheck(uri) {
  const current = runningChecks.get(uri);
  if (!current) {
    return;
  }
  runningChecks.delete(uri);
  try {
    current.kill();
  } catch {
    // Ignore process kill failures.
  }
}

/**
 * @param {number} value
 * @param {number} min
 * @param {number} max
 * @param {number} fallback
 * @returns {number}
 */
function clampNumber(value, min, max, fallback) {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.floor(value)));
}

/**
 * @param {string} candidate
 * @param {string} root
 * @returns {boolean}
 */
function isPathWithinRoot(candidate, root) {
  const normalizedRoot = path.resolve(root);
  const normalizedCandidate = path.resolve(candidate);
  const relative = path.relative(normalizedRoot, normalizedCandidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/**
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
function isSamePath(a, b) {
  return path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();
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
