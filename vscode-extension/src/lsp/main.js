const {
  createConnection,
  ProposedFeatures,
  TextDocuments,
  TextDocumentSyncKind,
} = require("vscode-languageserver/node");
const { TextDocument } = require("vscode-languageserver-textdocument");

const { DEFAULT_SETTINGS, normalizeSettings } = require("./config");
const { buildSymbolIndex } = require("./symbol-index");
const { createWorkspaceService } = require("./workspace");
const { createDiagnosticsService } = require("./diagnostics");
const { createCompletionHandler } = require("./completion");
const { createSymbolResolutionHandlers } = require("./symbol-resolution");

function startServer() {
  const connection = createConnection(ProposedFeatures.all);
  const documents = new TextDocuments(TextDocument);

  let settings = { ...DEFAULT_SETTINGS };
  const symbolCache = new Map();

  const getSettings = () => settings;

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

  const workspaceService = createWorkspaceService({
    documents,
    getSettings,
    getOrCreateSymbolIndex,
    buildSymbolIndex,
  });

  const diagnosticsService = createDiagnosticsService({
    connection,
    documents,
    getSettings,
  });

  const completionHandler = createCompletionHandler({
    documents,
    getOrCreateSymbolIndex,
    workspaceService,
    getSettings,
  });

  const symbolHandlers = createSymbolResolutionHandlers({
    documents,
    getOrCreateSymbolIndex,
    workspaceService,
  });

  connection.onInitialize((params) => {
    const init = params.initializationOptions || {};
    settings = normalizeSettings(init);
    workspaceService.trimExternalIndexCache();
    workspaceService.invalidateWorkspaceFileCache();

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
    workspaceService.invalidateWorkspaceFileCache();
    diagnosticsService.scheduleValidation(event.document, true);
  });

  documents.onDidChangeContent((event) => {
    symbolCache.delete(event.document.uri);
    if (!settings.runOnType) {
      return;
    }
    diagnosticsService.scheduleValidation(event.document, false);
  });

  documents.onDidSave((event) => {
    symbolCache.delete(event.document.uri);
    workspaceService.invalidateWorkspaceFileCache();
    diagnosticsService.scheduleValidation(event.document, true);
  });

  documents.onDidClose((event) => {
    diagnosticsService.clearDocumentState(event.document.uri);
    symbolCache.delete(event.document.uri);
    connection.sendDiagnostics({ uri: event.document.uri, diagnostics: [] });
  });

  connection.onCompletion(completionHandler);
  connection.onHover(symbolHandlers.onHover);
  connection.onSignatureHelp(symbolHandlers.onSignatureHelp);
  connection.onDefinition(symbolHandlers.onDefinition);
  connection.onReferences(symbolHandlers.onReferences);
  connection.onPrepareRename(symbolHandlers.onPrepareRename);
  connection.onRenameRequest(symbolHandlers.onRenameRequest);
  connection.onDocumentSymbol(symbolHandlers.onDocumentSymbol);
  connection.onWorkspaceSymbol(symbolHandlers.onWorkspaceSymbol);

  documents.listen(connection);
  connection.listen();
}

module.exports = {
  startServer,
};