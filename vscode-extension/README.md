# MIDORI VS Code Extension (Scaffold)

This folder contains a local scaffold for publishing MIDORI language support to Visual Studio Marketplace later.

## Included
- Language registration for `.mdr`
- Basic syntax highlighting (TextMate grammar)
- Editor language configuration (comments/brackets/auto-closing)
- Snippets
- Placeholder logo image (`assets/midori-logo.png`)

## Local Test
1. Open this folder in VS Code.
2. Press `F5` to launch Extension Development Host.
3. Open/create a `.mdr` file and verify highlighting/snippets.

## Before Publishing
- Update `publisher` in `package.json`
- Replace `assets/midori-logo.png` with final logo
- Set real `version`, `repository`, and metadata
- Add CI/publishing workflow for extension packaging (`vsce`)

This scaffold is intentionally not published.
