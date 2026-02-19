const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { TextDocument } = require("vscode-languageserver-textdocument");

const { uriToFilePath, isPathWithinRoot, isSamePath } = require("./utils-path");

const WORKSPACE_FILES_CACHE_TTL_MS = 4000;
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

function createWorkspaceService({ documents, getSettings, getOrCreateSymbolIndex, buildSymbolIndex }) {
  /** @type {Map<string, {mtimeMs: number, index: import("./symbol-index").SymbolIndex}>} */
  const externalIndexCache = new Map();
  let workspaceFileCache = {
    root: "",
    expiresAt: 0,
    files: [],
  };

  function touchExternalIndexCache(filePath, entry) {
    externalIndexCache.delete(filePath);
    externalIndexCache.set(filePath, entry);
  }

  function setExternalIndexCache(filePath, entry) {
    externalIndexCache.set(filePath, entry);
    trimExternalIndexCache();
  }

  function trimExternalIndexCache() {
    const settings = getSettings();
    while (externalIndexCache.size > settings.maxExternalIndexEntries) {
      const oldest = externalIndexCache.keys().next().value;
      if (!oldest) {
        break;
      }
      externalIndexCache.delete(oldest);
    }
  }

  function invalidateWorkspaceFileCache() {
    workspaceFileCache.expiresAt = 0;
  }

  async function getWorkspaceMidoriFiles() {
    const settings = getSettings();
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

  async function resolveImportPath(importSpec, currentFilePath) {
    const settings = getSettings();
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
        if (!settings.allowExternalImports && !isPathWithinRoot(normalized, settings.workspaceRoot)) {
          continue;
        }
        return normalized;
      } catch {
        // Try next candidate.
      }
    }
    return null;
  }

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

  async function collectImportedSymbols(index, currentFilePath) {
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
        collected.push(...importIndex.allSymbols);
      } catch {
        // Ignore bad imports in IntelliSense path and keep editor responsive.
      }
    }
    return collected;
  }

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

  return {
    getSettings,
    trimExternalIndexCache,
    invalidateWorkspaceFileCache,
    getWorkspaceMidoriFiles,
    resolveImportPath,
    getExternalSymbolIndex,
    collectImportedTopLevelSymbols,
    collectImportedSymbols,
    getDocumentContextByUri,
    getReferenceCandidateUris,
  };
}

module.exports = {
  createWorkspaceService,
};
