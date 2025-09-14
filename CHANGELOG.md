# 📑 Changelog

## [2.5.2] - 2025-09-15
### Added
- **Per-user custom prompts** support:
  - `/setprompt <text>` — set a custom prompt
  - `/clearprompt` — clear user prompt
- Persistent storage of prompts in `prompts.json` (survives restarts)
- Typing status emulation ("... is typing")
- Automatic splitting of long messages (>4000 characters)
- HTML formatting support (bold, italic, code, links, quotes, spoilers)

### Changed
- Dependency installation now uses `requirements.txt`
- Simplified multimedia handling (temporarily dropped ffmpeg for videos)
- Version updated → `2.5.2`

### Fixed
- Removed redundant imports and duplicate code
- Improved logging output ([INFO], [ERROR])

---

## [2.2.1] - 2025-09-12
### Added
- Initial bot release:
  - Text, voice, photo, and video support
  - Basic user memory
  - Automatic long-response splitting
  - Speech recognition & OCR
  - Markdown formatting support

---
