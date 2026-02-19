# MIDORI Language Support (Experimental)

Language support for MIDORI (`.mdr`) in Visual Studio Code.

Status: experimental. APIs and behavior can change between early versions.
Distribution: local/dev packaging today (`vsce package`), not published to Marketplace yet.

## Features

- MIDORI language registration for `.mdr`
- Syntax highlighting (TextMate grammar)
- Language configuration (comments, brackets, auto-closing pairs)
- Snippets (`main`, `fn`, `if`)
- Language server with:
  - live diagnostics (`midori check`)
  - completion (canonical keywords, fuzzy keyword suggestions, builtins, symbols, imports, import-paths)
  - hover info
  - signature help
  - go-to-definition
  - find references
  - rename symbol (scope-aware)
  - document symbols (outline)
  - workspace symbol search
- Canonical compiler keyword dictionary synced with lexer keywords
- Suggestion-only typo assistance for MIDORI keywords (no automatic source edits)
- Expanded symbol indexing for structs, fields, traits, and trait methods
- Problems-tab diagnostics with MIDORI error codes (`MDxxxx`)
- Built-in `$midori` problem matcher for task output parsing
- MIDORI file icon for `.mdr` (`assets/midori-logo.png`)
- `MIDORI: Restart Language Server` command

## What The Language Server Does

For diagnostics, the extension server runs the configured MIDORI command against a temporary file:

```text
<midori.lsp.command> <midori.lsp.args...> check <temp-file>
```

Compiler diagnostics are parsed and reported as editor squiggles and Problems entries.
For IntelliSense, the server builds bounded symbol indexes from open/imported/workspace `.mdr` files.
By default import resolution is sandboxed to the workspace root for safer indexing.

## Requirements

- MIDORI CLI installed and available from your configured command
- VS Code 1.85+

Default expected command is `midori`.

## Settings

- `midori.lsp.command`: default `"midori"`, example `"py"`
- `midori.lsp.args`: default `[]`, module-mode example `["-m", "midori_cli.main"]`
- `midori.diagnostics.runOnType`: default `true`
- `midori.diagnostics.debounceMs`: default `250` (minimum `50`)
- `midori.diagnostics.timeoutMs`: default `15000`
- `midori.diagnostics.maxOutputBytes`: default `262144`
- `midori.diagnostics.maxCount`: default `250`
- `midori.diagnostics.maxDocumentBytes`: default `2097152`
- `midori.intellisense.maxWorkspaceFiles`: default `1500`
- `midori.intellisense.maxExternalIndexEntries`: default `750`
- `midori.intellisense.allowExternalImports`: default `false`
- `midori.intellisense.fuzzyKeywordSuggestions`: default `true`
- `midori.intellisense.fuzzyMaxEditDistance`: default `2` (allowed `1..2`)

## Task-Based Diagnostics

You can use the contributed `$midori` problem matcher in `tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "MIDORI: Check Current File",
      "type": "shell",
      "command": "midori",
      "args": ["check", "${file}"],
      "problemMatcher": ["$midori"]
    }
  ]
}
```

## Current Limits

- IntelliSense is heuristic and focuses on practical local/imported symbol resolution
- Rename/references for heavily ambiguous symbols may be conservative to avoid unsafe edits
- Diagnostic fidelity depends on current compiler output format
- No formatter integration from the extension itself yet

## Local Development

```bash
npm install
npm run lint
npx @vscode/vsce package -o dist/midori-language-<version>.vsix
```

Installer scripts expect the extension bundle in `vscode-extension/dist/`.

Run in VS Code:

1. Open `vscode-extension/`.
2. Press `F5` to launch Extension Development Host.
3. Open `.mdr` files and confirm highlighting and diagnostics.

## Links

- Docs: https://midori-docs.vercel.app/
- Repo: https://github.com/ByteCraft-Co/MIDORI
- Issues: https://github.com/ByteCraft-Co/MIDORI/issues
