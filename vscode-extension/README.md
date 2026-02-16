# MIDORI VS Code Extension

Official language support for MIDORI (`.mdr`) in Visual Studio Code.

## Features
- Language registration for `.mdr`
- Syntax highlighting via TextMate grammar
- Bracket/comment/auto-closing language configuration
- Code snippets (`main`, `fn`, `if`)
- File icon theme mapping for `.mdr` files using `assets/midori-logo.png`

## Publisher
- Display: `bytecraft_bt`
- ID: `bytecraftbt`

## File Icon Behavior
This extension contributes the `MIDORI Icons` file icon theme and sets it as the default icon theme for MIDORI workspaces through `configurationDefaults`.

When installed, `.mdr` files are mapped to the MIDORI icon (`midori-logo.png`).

## Local Validation
```bash
npm run lint
npx @vscode/vsce package
```

## Development Host
1. Open `vscode-extension/` in VS Code.
2. Press `F5` to launch Extension Development Host.
3. Create/open `.mdr` files and verify highlighting and icon mapping.
