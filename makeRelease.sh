# Create a GitHub release based on the tag you just pushed
gh release create v0.7.7 \
  --title "ajsbsd v0.7.7" \
  --notes "### What's New in v0.7.7
- Refactored monolithic routing into a clean COMMAND_MAP dispatcher.
- Patched security vulnerabilities (plaintext password logging, XSS fallback).
- Fixed SECRET_KEY generation to prevent session resets on worker restarts.
- Added 'music' command with frontend audio integration.
- Updated README with integration and developer guides."
