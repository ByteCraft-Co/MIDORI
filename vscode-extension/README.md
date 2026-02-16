# MIDORI Language Support (Experimental)

Language support for MIDORI (`.mdr`) in Visual Studio Code.

Status: experimental. APIs and behavior can change between early versions.
Distribution: local/dev packaging today (`vsce package`), not published to Marketplace yet.

## Features

- MIDORI language registration for `.mdr`
- Syntax highlighting (TextMate grammar)
- Language configuration (comments, brackets, auto-closing pairs)
- Snippets (`main`, `fn`, `if`)
- Diagnostics-only language server with live `midori check` integration
- Problems-tab diagnostics with MIDORI error codes (`MDxxxx`)
- Built-in `$midori` problem matcher for task output parsing
- MIDORI file icon for `.mdr` (`assets/midori-logo.png`)
- `MIDORI: Restart Language Server` command

## What The Language Server Does

The extension server runs the configured MIDORI command against a temporary file:

```text
<midori.lsp.command> <midori.lsp.args...> check <temp-file>
```

Compiler diagnostics are parsed and reported as editor squiggles and Problems entries.

## Requirements

- MIDORI CLI installed and available from your configured command
- VS Code 1.85+

Default expected command is `midori`.

## Settings

- `midori.lsp.command`: default `"midori"`, example `"py"`
- `midori.lsp.args`: default `[]`, module-mode example `["-m", "midori_cli.main"]`
- `midori.diagnostics.runOnType`: default `true`
- `midori.diagnostics.debounceMs`: default `250` (minimum `50`)

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

- Diagnostics only (no completion, hover, go-to-definition, rename, or code actions)
- Diagnostic fidelity depends on current compiler output format
- No formatter integration from the extension itself yet

## Local Development

```bash
npm install
npm run lint
npx @vscode/vsce package
```

Run in VS Code:

1. Open `vscode-extension/`.
2. Press `F5` to launch Extension Development Host.
3. Open `.mdr` files and confirm highlighting and diagnostics.

## Links

- Docs: https://midori-docs.vercel.app/
- Repo: https://github.com/ByteCraft-Co/MIDORI
- Issues: https://github.com/ByteCraft-Co/MIDORI/issues
