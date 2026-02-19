const path = require("node:path");
const { CompletionItemKind } = require("vscode-languageserver/node");

const { uriToFilePath } = require("./utils-path");

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

async function provideImportPathCompletions(document, context, workspaceService) {
  const currentFilePath = uriToFilePath(document.uri);
  if (!currentFilePath) {
    return [];
  }

  const typedPath = context.typedPath;
  const slash = typedPath.lastIndexOf("/");
  const dirPrefix = slash >= 0 ? typedPath.slice(0, slash + 1) : "";
  const namePrefix = slash >= 0 ? typedPath.slice(slash + 1) : typedPath;
  const lookupDir = path.resolve(path.dirname(currentFilePath), dirPrefix || ".");

  const settings = workspaceService.getSettings();
  const { isPathWithinRoot } = require("./utils-path");
  if (!settings.allowExternalImports && !isPathWithinRoot(lookupDir, settings.workspaceRoot)) {
    return [];
  }

  let entries = [];
  try {
    entries = await require("node:fs/promises").readdir(lookupDir, { withFileTypes: true });
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

module.exports = {
  getImportCompletionContext,
  provideImportPathCompletions,
};