const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isIdentChar(ch) {
  return /[A-Za-z0-9_]/.test(ch);
}

function getIdentifierToken(document, position) {
  const source = document.getText();
  const lineStartOffset = document.offsetAt({ line: position.line, character: 0 });
  const lineEndOffset =
    position.line + 1 < document.lineCount
      ? document.offsetAt({ line: position.line + 1, character: 0 })
      : source.length;
  const lineText = source.slice(lineStartOffset, lineEndOffset).replace(/\r?\n$/, "");

  let startChar = Math.min(position.character, lineText.length);
  let endChar = Math.min(position.character, lineText.length);

  while (startChar > 0 && isIdentChar(lineText[startChar - 1])) {
    startChar -= 1;
  }
  while (endChar < lineText.length && isIdentChar(lineText[endChar])) {
    endChar += 1;
  }

  if (startChar === endChar) {
    return null;
  }
  const text = lineText.slice(startChar, endChar);
  if (!IDENT_RE.test(text)) {
    return null;
  }

  const start = { line: position.line, character: startChar };
  const end = { line: position.line, character: endChar };
  return {
    text,
    startOffset: document.offsetAt(start),
    endOffset: document.offsetAt(end),
    range: { start, end },
  };
}

function getIdentifierPrefixAtPosition(document, position) {
  const source = document.getText();
  const offset = document.offsetAt(position);
  let start = offset;
  while (start > 0 && isIdentChar(source[start - 1])) {
    start -= 1;
  }
  const value = source.slice(start, offset);
  return IDENT_RE.test(value) ? value : "";
}

function isInsideCommentOrString(source, offset) {
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = 0; i < offset; i += 1) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 1;
      }
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inString = true;
    }
  }

  return inString || inLineComment || inBlockComment;
}

function findMatchingBrace(source, openBraceOffset) {
  if (source[openBraceOffset] !== "{") {
    return -1;
  }
  let depth = 0;
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = openBraceOffset; i < source.length; i += 1) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 1;
      }
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{") {
      depth += 1;
      continue;
    }
    if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return i;
      }
    }
  }

  return -1;
}

function splitTopLevelSegments(text) {
  const out = [];
  let start = 0;
  let square = 0;
  let round = 0;
  let curly = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "[") {
      square += 1;
      continue;
    }
    if (ch === "]") {
      square = Math.max(0, square - 1);
      continue;
    }
    if (ch === "(") {
      round += 1;
      continue;
    }
    if (ch === ")") {
      round = Math.max(0, round - 1);
      continue;
    }
    if (ch === "{") {
      curly += 1;
      continue;
    }
    if (ch === "}") {
      curly = Math.max(0, curly - 1);
      continue;
    }

    if (ch === "," && square === 0 && round === 0 && curly === 0) {
      pushSegment(out, text, start, i);
      start = i + 1;
    }
  }

  pushSegment(out, text, start, text.length);
  return out;
}

function pushSegment(out, text, start, end) {
  const raw = text.slice(start, end);
  const leftTrim = raw.length - raw.trimStart().length;
  const rightTrim = raw.length - raw.trimEnd().length;
  const trimmed = raw.trim();
  if (!trimmed) {
    return;
  }
  out.push({
    text: trimmed,
    start: start + leftTrim,
    end: end - rightTrim,
  });
}

function findTopLevelChar(text, target) {
  let square = 0;
  let round = 0;
  let curly = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "[") {
      square += 1;
      continue;
    }
    if (ch === "]") {
      square = Math.max(0, square - 1);
      continue;
    }
    if (ch === "(") {
      round += 1;
      continue;
    }
    if (ch === ")") {
      round = Math.max(0, round - 1);
      continue;
    }
    if (ch === "{") {
      curly += 1;
      continue;
    }
    if (ch === "}") {
      curly = Math.max(0, curly - 1);
      continue;
    }

    if (ch === target && square === 0 && round === 0 && curly === 0) {
      return i;
    }
  }

  return -1;
}

function parseParameterList(text) {
  const params = [];
  for (const segment of splitTopLevelSegments(text)) {
    const colonIndex = findTopLevelChar(segment.text, ":");
    if (colonIndex < 0) {
      continue;
    }
    const name = segment.text.slice(0, colonIndex).trim();
    const type = normalizeTypeName(segment.text.slice(colonIndex + 1));
    if (!IDENT_RE.test(name) || !type) {
      continue;
    }
    params.push({ name, type });
  }
  return params;
}

function normalizeTypeName(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

function findActiveCall(source, offset) {
  const stack = [];
  let i = 0;
  let inString = false;
  let escaped = false;
  let inLineComment = false;
  let inBlockComment = false;
  let lastIdentifier = null;

  while (i < offset) {
    const ch = source[i];
    const next = i + 1 < source.length ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
      }
      i += 1;
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i += 2;
        continue;
      }
      i += 1;
      continue;
    }
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      i += 1;
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      lastIdentifier = null;
      i += 2;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      lastIdentifier = null;
      i += 2;
      continue;
    }
    if (ch === '"') {
      inString = true;
      lastIdentifier = null;
      i += 1;
      continue;
    }

    if (isIdentChar(ch)) {
      const start = i;
      i += 1;
      while (i < offset && isIdentChar(source[i])) {
        i += 1;
      }
      const text = source.slice(start, i);
      if (IDENT_RE.test(text)) {
        lastIdentifier = { text };
      } else {
        lastIdentifier = null;
      }
      continue;
    }

    if (ch === "(") {
      stack.push({
        name: lastIdentifier ? lastIdentifier.text : null,
        commas: 0,
      });
      lastIdentifier = null;
      i += 1;
      continue;
    }
    if (ch === ",") {
      const top = stack[stack.length - 1];
      if (top) {
        top.commas += 1;
      }
      lastIdentifier = null;
      i += 1;
      continue;
    }
    if (ch === ")") {
      if (stack.length > 0) {
        stack.pop();
      }
      lastIdentifier = null;
      i += 1;
      continue;
    }

    if (!/\s/.test(ch)) {
      lastIdentifier = null;
    }
    i += 1;
  }

  for (let j = stack.length - 1; j >= 0; j -= 1) {
    if (stack[j].name) {
      return {
        name: stack[j].name,
        activeParameter: stack[j].commas,
      };
    }
  }

  return null;
}

module.exports = {
  IDENT_RE,
  isIdentChar,
  getIdentifierToken,
  getIdentifierPrefixAtPosition,
  isInsideCommentOrString,
  findMatchingBrace,
  splitTopLevelSegments,
  findTopLevelChar,
  parseParameterList,
  normalizeTypeName,
  findActiveCall,
};