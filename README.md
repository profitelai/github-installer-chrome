# AI Dev Installer

A Chrome extension that installs any GitHub, PyPI, or npm package directly into VS Code with one click. No copy-pasting. No switching windows. No guessing the install command.

---

## How it works

1. You open any GitHub repo, PyPI package, or npm page in Chrome
2. Click the ⚡ extension icon
3. The extension reads the project README and auto-detects the real install command — `brew install`, `pip3 install`, `npm install`, `cargo install`, whatever the project actually uses
4. Click **Install** — VS Code opens, a terminal appears inside it, and the command runs right there

No more guessing. No more `pip install` on a project that uses Homebrew.

---

## Smart Detection

The extension fetches the project README from GitHub and scans for install commands in priority order:

```
brew → pipx → pip → npm → yarn → cargo → go → gem → curl → apt
```

- Shows a green **"from README"** badge when the command was detected (not guessed)
- Shows a dropdown if multiple install methods are found
- Falls back to `pip3 install git+<url>` only when nothing is found in the README

---

## Setup

### Requirements

- macOS (the bridge uses AppleScript to control VS Code)
- Python 3.8+
- VS Code installed
- Chrome

### Step 1 — Load the extension

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `ai-dev-installer` folder
5. The ⚡ icon appears in your toolbar — pin it

### Step 2 — Start the bridge server

The bridge is a local Python server on port 9876. It handles README fetching, install detection, and VS Code control.

```bash
python3 bridge/server.py
```

Keep it running in the background. You'll see:

```
AI Dev Installer bridge — http://localhost:9876
  pip:    pip3
  vscode: /Applications/Visual Studio Code.app/...
```

### Step 3 — Grant Accessibility permission (one-time)

The bridge uses AppleScript to open VS Code's integrated terminal. macOS requires one permission grant:

**System Settings → Privacy & Security → Accessibility → enable your Terminal app**

You'll be prompted automatically the first time.

---

## Usage

| Situation | What happens |
|-----------|-------------|
| GitHub repo | README is fetched, real install command detected |
| PyPI package | `pip3 install <name>` |
| npm package | `npm install <name>` |
| Any page (bridge offline) | Install command copied to clipboard |

**Keyboard shortcuts:**
- `⌘⇧V` — Install → VS Code
- `⌘⇧C` — Copy install command

---

## Files

```
ai-dev-installer/
├── manifest.json        Chrome extension manifest (v3)
├── popup.html           Extension popup UI
├── popup.js             Popup logic — detection, smart detect, install flow
├── content.js           Floating button injected on GitHub/PyPI/npm pages
├── content.css          Floating button styles
├── background.js        Service worker (keyboard shortcuts)
├── icons/               Extension icons (16/32/48/128px)
└── bridge/
    ├── server.py        Local HTTP server on port 9876
    └── start.sh         Convenience start script
```

---

## Bridge API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Check bridge + editor detection |
| `/smart-detect` | POST | Fetch README, extract install command |
| `/install` | POST | Run install command in VS Code terminal |
| `/open-editor` | POST | Open VS Code with a project folder |
| `/job/<id>` | GET | Poll install job status |

---

## Version History

| Version | Changes |
|---------|---------|
| 1.2.0 | Smart README detection — auto-detects brew/pip/npm/cargo. Installs run in VS Code integrated terminal. |
| 1.1.0 | One-click install + keyboard shortcuts + better editor detection |
| 1.0.0 | Initial release |

---

## License

MIT
