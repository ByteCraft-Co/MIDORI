const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const {
  createConnection,
  DiagnosticSeverity,
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

connection.onInitialize((params) => {
  const init = params.initializationOptions || {};
  settings = normalizeSettings(init);
  return {
    capabilities: {
      textDocumentSync: TextDocumentSyncKind.Incremental,
    },
  };
});

documents.onDidOpen((event) => {
  scheduleValidation(event.document, true);
});

documents.onDidChangeContent((event) => {
  if (!settings.runOnType) {
    return;
  }
  scheduleValidation(event.document, false);
});

documents.onDidSave((event) => {
  scheduleValidation(event.document, true);
});

documents.onDidClose((event) => {
  clearTimer(event.document.uri);
  connection.sendDiagnostics({ uri: event.document.uri, diagnostics: [] });
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
