# Privacy Policy — GitHub Installer Chrome Extension

**Last updated: July 2026**

## What this extension does

GitHub Installer is a Chrome extension that helps developers install GitHub repositories, PyPI packages, and npm packages directly into VS Code in one click.

## Data we collect

**We collect nothing.**

This extension does not collect, store, transmit, or share any personal data.

## What the extension accesses

| Access | Why | Sent to |
|--------|-----|---------|
| Current tab URL | To detect if you're on GitHub, PyPI, or npm | Nobody — stays in your browser |
| GitHub README (public) | To detect the correct install command | GitHub's public API only |
| localhost:9876 | To communicate with the local bridge server | Your own computer only |

## Third-party services

The extension makes requests to:
- **api.github.com** — to fetch public README files. This is the same data visible to anyone on GitHub. No authentication required. No account data accessed.

## Local bridge server

The `bridge/server.py` component runs entirely on your own machine at `localhost:9876`. It never contacts external servers. It opens VS Code using AppleScript on macOS.

## No tracking

- No analytics
- No cookies
- No user accounts
- No data stored in the cloud

## Contact

Questions? Open an issue at https://github.com/profitelai/github-installer-chrome
