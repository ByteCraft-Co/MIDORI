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
- MIDORI file icon for `.mdr` files (`assets/midori-logo.png`)

## Current Limits
- No full LSP features yet (go-to-definition, rename, symbol indexing)
- Diagnostics are limited compared to mature language toolchains
- Behavior may change across early releases

## File Icon Behavior
This extension contributes the `MIDORI Icons` theme and maps `.mdr` files to the MIDORI logo.
It does not override your active VS Code icon theme, so other file icons keep their normal appearance.
If you want the MIDORI-specific icon mapping, select `MIDORI Icons` manually in VS Code.

## Links
- Docs: https://midori-docs.vercel.app/
- Repo: https://github.com/ByteCraft-Co/MIDORI
- Issues: https://github.com/ByteCraft-Co/MIDORI/issues

## Local Validation
```bash
npm run lint
npx @vscode/vsce package
```

## Development Host
1. Open `vscode-extension/` in VS Code.
2. Press `F5` to launch Extension Development Host.
3. Create/open `.mdr` files and verify highlighting and icon mapping.
