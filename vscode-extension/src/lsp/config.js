const DEFAULT_SETTINGS = {
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
  fuzzyKeywordSuggestions: true,
  fuzzyMaxEditDistance: 2,
};

function normalizeSettings(input) {
  const command = typeof input.command === "string" ? input.command.trim() : DEFAULT_SETTINGS.command;
  const args = Array.isArray(input.args) ? input.args.filter((x) => typeof x === "string") : [];
  const runOnType = typeof input.runOnType === "boolean" ? input.runOnType : DEFAULT_SETTINGS.runOnType;
  const debounceMsRaw =
    typeof input.debounceMs === "number" ? input.debounceMs : DEFAULT_SETTINGS.debounceMs;
  const debounceMs = Math.max(50, Math.floor(debounceMsRaw));
  const diagnosticsTimeoutMs = clampNumber(
    typeof input.diagnosticsTimeoutMs === "number"
      ? input.diagnosticsTimeoutMs
      : DEFAULT_SETTINGS.diagnosticsTimeoutMs,
    2000,
    120000,
    DEFAULT_SETTINGS.diagnosticsTimeoutMs,
  );
  const diagnosticsMaxOutputBytes = clampNumber(
    typeof input.diagnosticsMaxOutputBytes === "number"
      ? input.diagnosticsMaxOutputBytes
      : DEFAULT_SETTINGS.diagnosticsMaxOutputBytes,
    64 * 1024,
    2 * 1024 * 1024,
    DEFAULT_SETTINGS.diagnosticsMaxOutputBytes,
  );
  const diagnosticsMaxCount = clampNumber(
    typeof input.diagnosticsMaxCount === "number"
      ? input.diagnosticsMaxCount
      : DEFAULT_SETTINGS.diagnosticsMaxCount,
    1,
    1000,
    DEFAULT_SETTINGS.diagnosticsMaxCount,
  );
  const maxDocumentBytes = clampNumber(
    typeof input.maxDocumentBytes === "number"
      ? input.maxDocumentBytes
      : DEFAULT_SETTINGS.maxDocumentBytes,
    64 * 1024,
    5 * 1024 * 1024,
    DEFAULT_SETTINGS.maxDocumentBytes,
  );
  const maxWorkspaceFiles = clampNumber(
    typeof input.maxWorkspaceFiles === "number"
      ? input.maxWorkspaceFiles
      : DEFAULT_SETTINGS.maxWorkspaceFiles,
    100,
    15000,
    DEFAULT_SETTINGS.maxWorkspaceFiles,
  );
  const maxExternalIndexEntries = clampNumber(
    typeof input.maxExternalIndexEntries === "number"
      ? input.maxExternalIndexEntries
      : DEFAULT_SETTINGS.maxExternalIndexEntries,
    100,
    5000,
    DEFAULT_SETTINGS.maxExternalIndexEntries,
  );
  const allowExternalImports = Boolean(input.allowExternalImports);
  const fuzzyKeywordSuggestions =
    typeof input.fuzzyKeywordSuggestions === "boolean"
      ? input.fuzzyKeywordSuggestions
      : DEFAULT_SETTINGS.fuzzyKeywordSuggestions;
  const fuzzyMaxEditDistance = clampNumber(
    typeof input.fuzzyMaxEditDistance === "number"
      ? input.fuzzyMaxEditDistance
      : DEFAULT_SETTINGS.fuzzyMaxEditDistance,
    1,
    2,
    DEFAULT_SETTINGS.fuzzyMaxEditDistance,
  );
  const workspaceRootRaw =
    typeof input.workspaceRoot === "string" && input.workspaceRoot.trim().length > 0
      ? input.workspaceRoot
      : process.cwd();
  const workspaceRoot = require("node:path").resolve(workspaceRootRaw);

  return {
    command: command || DEFAULT_SETTINGS.command,
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
    fuzzyKeywordSuggestions,
    fuzzyMaxEditDistance,
  };
}

function clampNumber(value, min, max, fallback) {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.floor(value)));
}

module.exports = {
  DEFAULT_SETTINGS,
  normalizeSettings,
  clampNumber,
};