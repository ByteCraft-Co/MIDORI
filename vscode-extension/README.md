# MIDORI Language Support (Experimental)

Language support for MIDORI (`.mdr`) in Visual Studio Code.

> Status: **Experimental**
> MIDORI is still evolving and is not yet recommended for production-critical or fully dependent workflows.
> The current focus is education, language experimentation, and learning compiler concepts.

## Features
- Registers the MIDORI language for `.mdr` files
- Syntax highlighting via TextMate grammar
- Bracket/comment/auto-closing language configuration
- Starter snippets (`main`, `fn`, `if`)
- Diagnostics-only Language Server: live parse/type/borrow diagnostics with red squiggles
- Problems tab integration from compiler diagnostics and error codes (`MDxxxx`)
- Contributed problem matcher (`$midori`) for task-based `check`/`build` runs
- MIDORI file icon for `.mdr` files (`assets/midori-logo.png`)

## Current Limits
- LSP currently provides diagnostics only (no go-to-definition, rename, completion, hover)
- Diagnostics are limited compared to mature language toolchains
- Behavior may change across early releases

## File Icon Behavior
This extension does not force or replace your active icon theme.
`.mdr` files use the MIDORI language icon (`midori-logo.png`) while other file types continue using your normal icon theme.

## Links
- Docs: https://midori-docs.vercel.app/
- Repo: https://github.com/ByteCraft-Co/MIDORI
- Issues: https://github.com/ByteCraft-Co/MIDORI/issues

## Diagnostics Settings
- `midori.lsp.command` (default: `midori`)
- `midori.lsp.args` (default: `[]`, example: `["-m", "midori_cli.main"]` when using `py`)
- `midori.diagnostics.runOnType` (default: `true`)
- `midori.diagnostics.debounceMs` (default: `250`)

## Task-Based Diagnostics
Use the MIDORI problem matcher in workspace tasks to surface diagnostics from CLI runs:

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

## Local Validation
```bash
npm install
npm run lint
npx @vscode/vsce package
```

## Development Host
1. Open `vscode-extension/` in VS Code.
2. Press `F5` to launch Extension Development Host.
3. Create/open `.mdr` files and verify highlighting and live diagnostics.
