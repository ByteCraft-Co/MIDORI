const {
  findMatchingBrace,
  parseParameterList,
  normalizeTypeName,
  splitTopLevelSegments,
} = require("./utils-text");

/**
 * @typedef {"function" | "param" | "local" | "enum" | "variant" | "error" | "struct" | "field" | "trait" | "method"} SymbolKindTag
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
 *   structs: MidoriSymbol[],
 *   structFields: MidoriSymbol[],
 *   traits: MidoriSymbol[],
 *   traitMethods: MidoriSymbol[],
 *   params: MidoriSymbol[],
 *   locals: MidoriSymbol[],
 *   topLevelSymbols: MidoriSymbol[],
 *   allSymbols: MidoriSymbol[],
 * }} SymbolIndex
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
    structs: [],
    structFields: [],
    traits: [],
    traitMethods: [],
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

  const structRe = /\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{/g;
  for (const match of source.matchAll(structRe)) {
    const structName = match[1];
    if (!structName) {
      continue;
    }
    const structNameOffset = match.index + match[0].indexOf(structName);
    const openBraceOffset = match.index + match[0].lastIndexOf("{");
    const closeBraceOffset = findMatchingBrace(source, openBraceOffset);
    index.structs.push(
      createSymbol(document, {
        name: structName,
        kind: "struct",
        offset: structNameOffset,
      }),
    );

    if (closeBraceOffset < 0) {
      continue;
    }

    const bodyText = source.slice(openBraceOffset + 1, closeBraceOffset);
    const bodyOffset = openBraceOffset + 1;
    const fieldRe = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^,\n\r}]+)\s*(?:,)?\s*$/gm;
    for (const fieldMatch of bodyText.matchAll(fieldRe)) {
      const fieldName = fieldMatch[1];
      if (!fieldName) {
        continue;
      }
      const fieldType = normalizeTypeName(fieldMatch[2] || "");
      const fieldOffset = bodyOffset + fieldMatch.index + fieldMatch[0].indexOf(fieldName);
      index.structFields.push(
        createSymbol(document, {
          name: fieldName,
          kind: "field",
          container: structName,
          type: fieldType || undefined,
          offset: fieldOffset,
        }),
      );
    }
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

  const traitRe = /\btrait\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{/g;
  for (const match of source.matchAll(traitRe)) {
    const traitName = match[1];
    if (!traitName) {
      continue;
    }
    const traitNameOffset = match.index + match[0].indexOf(traitName);
    const openBraceOffset = match.index + match[0].lastIndexOf("{");
    const closeBraceOffset = findMatchingBrace(source, openBraceOffset);
    index.traits.push(
      createSymbol(document, {
        name: traitName,
        kind: "trait",
        offset: traitNameOffset,
      }),
    );

    if (closeBraceOffset < 0) {
      continue;
    }

    const bodyText = source.slice(openBraceOffset + 1, closeBraceOffset);
    const bodyOffset = openBraceOffset + 1;
    const methodRe =
      /\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)\s*(?:->\s*([^;\n\r{]+))?/g;

    for (const methodMatch of bodyText.matchAll(methodRe)) {
      const methodName = methodMatch[1];
      if (!methodName) {
        continue;
      }
      const params = parseParameterList(methodMatch[2] || "");
      const returnType = normalizeTypeName(methodMatch[3] || "Void");
      const methodOffset = bodyOffset + methodMatch.index + methodMatch[0].indexOf(methodName);
      const signature = `${methodName}(${formatCallableParams(params)}) -> ${returnType}`;
      index.traitMethods.push(
        createSymbol(document, {
          name: methodName,
          kind: "method",
          container: traitName,
          params,
          signature,
          returnType,
          offset: methodOffset,
        }),
      );
    }
  }

  const externRanges = [];
  const externFnRe =
    /\bextern(?:\s+"[^"]*")?\s+fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)\s*(?:->\s*([^\n{]+))?/g;
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
    /\b(?:pub\s+)?(?:task\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)\s*(?:->\s*([^{\n]+))?\s*\{/g;
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

  index.topLevelSymbols = [
    ...index.functions,
    ...index.structs,
    ...index.enums,
    ...index.traits,
    ...index.variants,
    ...index.errors,
  ];
  index.allSymbols = [
    ...index.topLevelSymbols,
    ...index.structFields,
    ...index.traitMethods,
    ...index.params,
    ...index.locals,
  ];

  return index;
}

function createSymbol(document, input) {
  const start = document.positionAt(input.offset);
  const end = document.positionAt(input.offset + input.name.length);
  return {
    ...input,
    uri: document.uri,
    range: { start, end },
  };
}

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

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function offsetToLocation(document, offset, length) {
  return {
    uri: document.uri,
    range: {
      start: document.positionAt(offset),
      end: document.positionAt(offset + length),
    },
  };
}

function symbolToLocation(symbol) {
  return {
    uri: symbol.uri,
    range: symbol.range,
  };
}

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

function isSameSymbol(a, b) {
  return (
    a.uri === b.uri
    && a.range.start.line === b.range.start.line
    && a.range.start.character === b.range.start.character
  );
}

function isSameLocation(a, b) {
  return (
    a.uri === b.uri
    && a.range.start.line === b.range.start.line
    && a.range.start.character === b.range.start.character
  );
}

function isInsideRanges(start, ranges) {
  for (const item of ranges) {
    if (start >= item.start && start <= item.end) {
      return true;
    }
  }
  return false;
}

function formatCallableParams(params) {
  if (!params || params.length === 0) {
    return "";
  }
  return params.map((item) => `${item.name}: ${item.type}`).join(", ");
}

module.exports = {
  buildSymbolIndex,
  createSymbol,
  getSymbolsInScope,
  findEnclosingFunction,
  findBestLocalSymbol,
  collectIdentifierOffsets,
  offsetToLocation,
  symbolToLocation,
  dedupeLocations,
  isSameSymbol,
  isSameLocation,
  isInsideRanges,
  formatCallableParams,
};
