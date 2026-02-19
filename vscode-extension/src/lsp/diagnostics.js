const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { DiagnosticSeverity } = require("vscode-languageserver/node");

function createDiagnosticsService({ connection, documents, getSettings }) {
  /** @type {Map<string, NodeJS.Timeout>} */
  const timers = new Map();
  /** @type {Map<string, number>} */
  const versions = new Map();
  /** @type {Map<string, import("node:child_process").ChildProcess>} */
  const runningChecks = new Map();

  function scheduleValidation(document, immediate) {
    const settings = getSettings();
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

  function clearDocumentState(uri) {
    clearTimer(uri);
    cancelRunningCheck(uri);
    versions.delete(uri);
  }

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

  async function validateDocument(document) {
    const token = (versions.get(document.uri) || 0) + 1;
    versions.set(document.uri, token);
    clearTimer(document.uri);
    cancelRunningCheck(document.uri);

    try {
      const diagnostics = await runCheck(document, token);
      const current = documents.get(document.uri);
      const isStale =
        !current || versions.get(document.uri) !== token || current.version !== document.version;
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
    const settings = getSettings();
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
    const settings = getSettings();
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

  return {
    scheduleValidation,
    clearDocumentState,
    cancelRunningCheck,
  };
}

function parseDiagnostics(output) {
  const diagnostics = [];
  const lines = output.split(/\r?\n/);
  let last = null;

  for (const line of lines) {
    if (!line || line.length > 5000) {
      continue;
    }

    const match = line.match(/^(.+):(\d+):(\d+):\s(error|warning)(?:\[(MD\d{4})\])?:\s(.*)$/);
    if (match) {
      const lineNum = Math.max(0, Number(match[2]) - 1);
      const colNum = Math.max(0, Number(match[3]) - 1);
      const severity = match[4] === "warning" ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error;
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

module.exports = {
  createDiagnosticsService,
  parseDiagnostics,
};