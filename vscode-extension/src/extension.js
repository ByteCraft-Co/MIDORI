const path = require("node:path");
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function readInitializationOptions() {
  const config = vscode.workspace.getConfiguration("midori");
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  return {
    command: config.get("lsp.command", "midori"),
    args: config.get("lsp.args", []),
    runOnType: config.get("diagnostics.runOnType", true),
    debounceMs: config.get("diagnostics.debounceMs", 250),
    diagnosticsTimeoutMs: config.get("diagnostics.timeoutMs", 15000),
    diagnosticsMaxOutputBytes: config.get("diagnostics.maxOutputBytes", 262144),
    diagnosticsMaxCount: config.get("diagnostics.maxCount", 250),
    maxDocumentBytes: config.get("diagnostics.maxDocumentBytes", 2097152),
    maxWorkspaceFiles: config.get("intellisense.maxWorkspaceFiles", 1500),
    maxExternalIndexEntries: config.get("intellisense.maxExternalIndexEntries", 750),
    allowExternalImports: config.get("intellisense.allowExternalImports", false),
    fuzzyKeywordSuggestions: config.get("intellisense.fuzzyKeywordSuggestions", true),
    fuzzyMaxEditDistance: config.get("intellisense.fuzzyMaxEditDistance", 2),
    workspaceRoot: folder || process.cwd(),
  };
}

async function startClient(context) {
  if (client) {
    return;
  }
  const serverModule = context.asAbsolutePath(path.join("src", "server.js"));
  const serverOptions = {
    run: { module: serverModule, transport: TransportKind.stdio },
    debug: { module: serverModule, transport: TransportKind.stdio },
  };

  const clientOptions = {
    documentSelector: [
      { scheme: "file", language: "midori" },
      { scheme: "untitled", language: "midori" },
    ],
    initializationOptions: readInitializationOptions(),
  };

  client = new LanguageClient(
    "midoriLanguageServer",
    "MIDORI Language Server",
    serverOptions,
    clientOptions,
  );
  await client.start();
}

async function stopClient() {
  if (!client) {
    return;
  }
  const current = client;
  client = undefined;
  await current.stop();
}

/**
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
  await startClient(context);

  context.subscriptions.push(
    vscode.commands.registerCommand("midori.restartLanguageServer", async () => {
      await stopClient();
      await startClient(context);
      vscode.window.showInformationMessage("MIDORI language server restarted.");
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (event) => {
      if (!event.affectsConfiguration("midori")) {
        return;
      }
      await stopClient();
      await startClient(context);
    }),
  );
}

async function deactivate() {
  await stopClient();
}

module.exports = {
  activate,
  deactivate,
};
