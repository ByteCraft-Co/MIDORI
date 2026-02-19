const {
  CompletionItemKind,
  InsertTextFormat,
  MarkupKind,
} = require("vscode-languageserver/node");

const { KEYWORDS, TYPE_NAMES, BUILTIN_FUNCTIONS } = require("./lexicon");
const { rankKeywordSuggestions } = require("./fuzzy");
const { getImportCompletionContext, provideImportPathCompletions } = require("./import-completion");
const { getIdentifierPrefixAtPosition, isInsideCommentOrString } = require("./utils-text");
const { uriToFilePath } = require("./utils-path");
const { getSymbolsInScope, formatCallableParams } = require("./symbol-index");

function buildKeywordCompletionItems(prefix, options = {}) {
  const normalizedPrefix = (prefix || "").trim();
  const lowerPrefix = normalizedPrefix.toLowerCase();
  const fuzzyEnabled = options.fuzzyEnabled !== false;
  const maxEditDistance = Number.isFinite(options.maxEditDistance) ? options.maxEditDistance : 2;

  const byKeyword = new Map();
  for (const keyword of KEYWORDS) {
    const startsWith = lowerPrefix && keyword.toLowerCase().startsWith(lowerPrefix);
    byKeyword.set(keyword, {
      label: keyword,
      kind: CompletionItemKind.Keyword,
      detail: "MIDORI keyword",
      sortText: startsWith ? `0_${keyword}` : `2_${keyword}`,
    });
  }

  if (!fuzzyEnabled || !lowerPrefix || KEYWORDS.includes(normalizedPrefix)) {
    return byKeyword;
  }

  const ranked = rankKeywordSuggestions(lowerPrefix, KEYWORDS, maxEditDistance);
  for (let i = 0; i < ranked.length; i += 1) {
    const item = ranked[i];
    const existing = byKeyword.get(item.keyword);
    if (!existing) {
      continue;
    }

    const rankSuffix = String(i).padStart(3, "0");
    if (item.startsWith) {
      existing.sortText = `0_${rankSuffix}_${item.keyword}`;
      continue;
    }

    existing.sortText = `1_${rankSuffix}_${item.keyword}`;
    existing.detail = "MIDORI keyword suggestion";
    if (i === 0) {
      existing.preselect = true;
    }
  }

  return byKeyword;
}

function createCompletionHandler({ documents, getOrCreateSymbolIndex, workspaceService, getSettings }) {
  return async function onCompletion(params) {
    const document = documents.get(params.textDocument.uri);
    if (!document) {
      return [];
    }

    const source = document.getText();
    const offset = document.offsetAt(params.position);

    const importContext = getImportCompletionContext(document, params.position);
    if (importContext) {
      return provideImportPathCompletions(document, importContext, workspaceService);
    }
    if (isInsideCommentOrString(source, offset)) {
      return [];
    }

    const settings = getSettings();
    const prefix = getIdentifierPrefixAtPosition(document, params.position);
    const index = getOrCreateSymbolIndex(document);
    const completionItems = new Map();

    const keywordItems = buildKeywordCompletionItems(prefix, {
      fuzzyEnabled: settings.fuzzyKeywordSuggestions,
      maxEditDistance: settings.fuzzyMaxEditDistance,
    });
    for (const [label, item] of keywordItems.entries()) {
      completionItems.set(label, item);
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
      const imported = await workspaceService.collectImportedTopLevelSymbols(index, currentFilePath);
      for (const symbol of imported) {
        if (!completionItems.has(symbol.name)) {
          completionItems.set(symbol.name, toCompletionItem(symbol));
        }
      }
    }

    return Array.from(completionItems.values());
  };
}

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
  if (symbol.kind === "method") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Method,
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
  if (symbol.kind === "struct") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Struct,
      detail: "struct",
    };
  }
  if (symbol.kind === "trait") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Interface,
      detail: "trait",
    };
  }
  if (symbol.kind === "field") {
    return {
      label: symbol.name,
      kind: CompletionItemKind.Field,
      detail: symbol.container ? `${symbol.container} field` : "field",
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

function buildCallSnippet(name, params) {
  if (!params || params.length === 0) {
    return `${name}()`;
  }
  const placeholders = params.map((item, i) => "${" + String(i + 1) + ":" + item.name + "}");
  return `${name}(${placeholders.join(", ")})`;
}

module.exports = {
  buildKeywordCompletionItems,
  createCompletionHandler,
  toCompletionItem,
};
