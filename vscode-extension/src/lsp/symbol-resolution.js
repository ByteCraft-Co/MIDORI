const { MarkupKind, SymbolKind } = require("vscode-languageserver/node");

const { BUILTIN_FUNCTION_MAP, getKeywordDoc, isKeyword } = require("./lexicon");
const {
  IDENT_RE,
  getIdentifierToken,
  isInsideCommentOrString,
  findActiveCall,
} = require("./utils-text");
const { uriToFilePath } = require("./utils-path");
const {
  findBestLocalSymbol,
  symbolToLocation,
  dedupeLocations,
  collectIdentifierOffsets,
  offsetToLocation,
  isSameLocation,
  isSameSymbol,
  formatCallableParams,
} = require("./symbol-index");

const MAX_WORKSPACE_SYMBOL_RESULTS = 250;
const MAX_REFERENCE_RESULTS = 750;

function createSymbolResolutionHandlers({ documents, getOrCreateSymbolIndex, workspaceService }) {
  return {
    onHover: async (params) => {
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
      const symbol = await resolveSymbolForHover(document, index, token.text, token.startOffset, workspaceService);
      if (!symbol) {
        return null;
      }

      return {
        range: token.range,
        contents: buildHoverContents(symbol),
      };
    },

    onSignatureHelp: async (params) => {
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
      const callable = await resolveCallable(document, index, activeCall.name, workspaceService);
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
    },

    onDefinition: async (params) => {
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
      const locations = await resolveDefinitionLocations(
        document,
        index,
        token.text,
        token.startOffset,
        workspaceService,
      );
      if (locations.length === 0) {
        return null;
      }
      return locations.length === 1 ? locations[0] : locations;
    },

    onReferences: async (params) => {
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
      const target = await resolveRenameTarget(
        document,
        index,
        token.text,
        token.startOffset,
        workspaceService,
      );
      if (!target) {
        return [];
      }

      return findReferenceLocations(target, token.text, {
        includeDeclaration: params.context.includeDeclaration,
        workspaceService,
      });
    },

    onPrepareRename: async (params) => {
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
      if (isKeyword(token.text) || BUILTIN_FUNCTION_MAP.has(token.text)) {
        return null;
      }

      const index = getOrCreateSymbolIndex(document);
      const target = await resolveRenameTarget(
        document,
        index,
        token.text,
        token.startOffset,
        workspaceService,
      );
      if (!target) {
        return null;
      }
      return {
        range: token.range,
        placeholder: token.text,
      };
    },

    onRenameRequest: async (params) => {
      const newName = (params.newName || "").trim();
      if (!IDENT_RE.test(newName) || isKeyword(newName)) {
        return { changes: {} };
      }

      const document = documents.get(params.textDocument.uri);
      if (!document) {
        return { changes: {} };
      }
      const token = getIdentifierToken(document, params.position);
      if (!token) {
        return { changes: {} };
      }
      if (isInsideCommentOrString(document.getText(), token.startOffset)) {
        return { changes: {} };
      }

      const index = getOrCreateSymbolIndex(document);
      const target = await resolveRenameTarget(
        document,
        index,
        token.text,
        token.startOffset,
        workspaceService,
      );
      if (!target) {
        return { changes: {} };
      }

      const references = await findReferenceLocations(target, token.text, {
        includeDeclaration: true,
        workspaceService,
      });
      return buildWorkspaceEditForRename(references, newName);
    },

    onDocumentSymbol: (params) => {
      const document = documents.get(params.textDocument.uri);
      if (!document) {
        return [];
      }
      const index = getOrCreateSymbolIndex(document);
      return buildDocumentSymbols(document, index);
    },

    onWorkspaceSymbol: async (params) => {
      return queryWorkspaceSymbols(params.query || "", workspaceService);
    },
  };
}

async function resolveSymbolForHover(document, index, name, offset, workspaceService) {
  const local = findBestLocalSymbol(index, name, offset);
  if (local) {
    return local;
  }

  const localAny = index.allSymbols.find((symbol) => symbol.name === name);
  if (localAny) {
    return localAny;
  }

  const currentFilePath = uriToFilePath(document.uri);
  if (currentFilePath) {
    const imported = await workspaceService.collectImportedSymbols(index, currentFilePath);
    const importedSymbol = imported.find((symbol) => symbol.name === name);
    if (importedSymbol) {
      return importedSymbol;
    }
  }

  const builtin = BUILTIN_FUNCTION_MAP.get(name);
  if (builtin) {
    return builtin;
  }

  const keywordDoc = getKeywordDoc(name);
  if (keywordDoc) {
    return {
      keyword: name,
      documentation: keywordDoc,
    };
  }

  return null;
}

async function resolveCallable(document, index, name, workspaceService) {
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

  const method = index.traitMethods.find((symbol) => symbol.name === name);
  if (method) {
    return {
      label: `${method.name}(${formatCallableParams(method.params || [])}) -> ${method.returnType || "Void"}`,
      params: method.params || [],
      documentation: method.container ? `Trait method in \`${method.container}\`.` : "Trait method.",
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

  const imported = await workspaceService.collectImportedSymbols(index, currentFilePath);
  const importedCallable = imported.find(
    (symbol) => symbol.name === name && ["function", "variant", "method"].includes(symbol.kind),
  );
  if (!importedCallable) {
    return null;
  }

  return {
    label: `${importedCallable.name}(${formatCallableParams(importedCallable.params || [])}) -> ${importedCallable.returnType || importedCallable.container || "Void"}`,
    params: importedCallable.params || [],
  };
}

async function resolveDefinitionLocations(document, index, name, offset, workspaceService) {
  const local = findBestLocalSymbol(index, name, offset);
  if (local) {
    return [symbolToLocation(local)];
  }

  const topLevelLocal = index.allSymbols.filter((symbol) => symbol.name === name);
  if (topLevelLocal.length > 0) {
    return dedupeLocations(topLevelLocal.map(symbolToLocation));
  }

  const currentFilePath = uriToFilePath(document.uri);
  if (!currentFilePath) {
    return [];
  }

  const imported = await workspaceService.collectImportedSymbols(index, currentFilePath);
  const importedMatches = imported.filter((symbol) => symbol.name === name);
  return dedupeLocations(importedMatches.map(symbolToLocation));
}

function buildHoverContents(symbol) {
  if (symbol.keyword) {
    return {
      kind: MarkupKind.Markdown,
      value: `\`\`\`midori\n${symbol.keyword}\n\`\`\`\n${symbol.documentation}`,
    };
  }

  if ("kind" in symbol) {
    if (symbol.kind === "function") {
      const label = symbol.signature || `${symbol.name}() -> ${symbol.returnType || "Void"}`;
      const externNote = symbol.isExtern ? "\nExtern declaration." : "";
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nfn ${label}\n\`\`\`${externNote}`,
      };
    }
    if (symbol.kind === "method") {
      const detail = symbol.container ? `\nTrait: \`${symbol.container}\`` : "";
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nfn ${symbol.signature || symbol.name}\n\`\`\`${detail}`,
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
    if (symbol.kind === "struct") {
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\nstruct ${symbol.name}\n\`\`\``,
      };
    }
    if (symbol.kind === "trait") {
      return {
        kind: MarkupKind.Markdown,
        value: `\`\`\`midori\ntrait ${symbol.name}\n\`\`\``,
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

async function resolveRenameTarget(document, index, name, offset, workspaceService) {
  const symbol = await resolveSymbolForHover(document, index, name, offset, workspaceService);
  if (!symbol || !("kind" in symbol)) {
    return null;
  }
  if (["field", "method"].includes(symbol.kind) && !symbol.container) {
    return null;
  }
  return symbol;
}

async function findReferenceLocations(target, name, options) {
  const { includeDeclaration, workspaceService } = options;

  if (target.kind === "local" || target.kind === "param") {
    const context = await workspaceService.getDocumentContextByUri(target.uri);
    if (!context) {
      return includeDeclaration ? [symbolToLocation(target)] : [];
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

    if (includeDeclaration) {
      found.push(symbolToLocation(target));
    }
    return dedupeLocations(found);
  }

  const targetDefinition = symbolToLocation(target);
  const candidateUris = await workspaceService.getReferenceCandidateUris(target);
  const out = [];

  for (const uri of candidateUris) {
    const context = await workspaceService.getDocumentContextByUri(uri);
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
        workspaceService,
      );
      if (!defs.some((location) => isSameLocation(location, targetDefinition))) {
        continue;
      }

      const location = offsetToLocation(context.document, offset, name.length);
      if (!includeDeclaration && isSameLocation(location, targetDefinition)) {
        continue;
      }
      out.push(location);
      if (out.length >= MAX_REFERENCE_RESULTS) {
        return dedupeLocations(out);
      }
    }
  }

  if (includeDeclaration) {
    out.push(targetDefinition);
  }
  return dedupeLocations(out);
}

function buildWorkspaceEditForRename(references, newName) {
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

function buildDocumentSymbols(document, index) {
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

  const structs = [...index.structs].sort((a, b) => a.offset - b.offset);
  for (const item of structs) {
    const structSymbol = {
      name: item.name,
      kind: SymbolKind.Struct,
      range: item.range,
      selectionRange: item.range,
      children: [],
    };

    const fields = index.structFields
      .filter((field) => field.container === item.name)
      .sort((a, b) => a.offset - b.offset);
    for (const field of fields) {
      structSymbol.children.push({
        name: field.name,
        detail: field.type || undefined,
        kind: SymbolKind.Field,
        range: field.range,
        selectionRange: field.range,
      });
    }

    symbols.push(structSymbol);
  }

  const traits = [...index.traits].sort((a, b) => a.offset - b.offset);
  for (const item of traits) {
    const traitSymbol = {
      name: item.name,
      kind: SymbolKind.Interface,
      range: item.range,
      selectionRange: item.range,
      children: [],
    };

    const methods = index.traitMethods
      .filter((method) => method.container === item.name)
      .sort((a, b) => a.offset - b.offset);
    for (const method of methods) {
      traitSymbol.children.push({
        name: method.name,
        detail: method.signature || undefined,
        kind: SymbolKind.Method,
        range: method.range,
        selectionRange: method.range,
      });
    }

    symbols.push(traitSymbol);
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

async function queryWorkspaceSymbols(query, workspaceService) {
  const normalizedQuery = query.trim().toLowerCase();
  const files = await workspaceService.getWorkspaceMidoriFiles();
  const results = [];

  for (const filePath of files) {
    const uri = require("node:url").pathToFileURL(filePath).toString();
    const context = await workspaceService.getDocumentContextByUri(uri);
    if (!context) {
      continue;
    }

    const symbols = [
      ...context.index.topLevelSymbols,
      ...context.index.structFields,
      ...context.index.traitMethods,
    ];

    for (const symbol of symbols) {
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

function toLspSymbolKind(kind) {
  if (kind === "function") {
    return SymbolKind.Function;
  }
  if (kind === "method") {
    return SymbolKind.Method;
  }
  if (kind === "struct") {
    return SymbolKind.Struct;
  }
  if (kind === "field") {
    return SymbolKind.Field;
  }
  if (kind === "trait") {
    return SymbolKind.Interface;
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

module.exports = {
  createSymbolResolutionHandlers,
  resolveDefinitionLocations,
  buildDocumentSymbols,
  queryWorkspaceSymbols,
  toLspSymbolKind,
};