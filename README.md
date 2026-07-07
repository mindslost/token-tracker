# Token Tracker GNOME Extension

A native GNOME Shell Extension to monitor rate limits, credit balances, and reset times for AI coding assistants. This project is a Linux/GNOME clone of the popular macOS menu bar app [CodexBar](https://github.com/steipete/CodexBar).

The initial MVP supports **Google Antigravity** by auto-detecting the local running language server/CLI and fetching real-time quotas.

---

## Architecture

This application consists of two decoupled parts to ensure optimal shell performance and security:
1. **Python CLI Helper (`cli/token_tracker_cli.py`)**: A standalone script that runs on-demand or background, scans system processes, maps network ports, and queries provider APIs. This prevents blocking the main thread of GNOME Shell.
2. **GNOME Shell Extension (GNOME 45+)**: A lightweight status panel button that executes the Python CLI helper asynchronously, displaying progress bars and countdown timers in a dropdown menu.

---

## Installation

### 1. Install the Extension
Run the following command inside the project directory to copy the extension to the local GNOME extensions directory:
```bash
make install
```

### 2. Restart GNOME Shell
* **X11**: Press `Alt + F2`, type `r`, and press `Enter`.
* **Wayland**: Log out and log back in.

### 3. Enable the Extension
Enable the extension using:
```bash
make enable
```

---

## Development & Testing

### Testing the Python CLI Helper
To test the CLI locally to verify it detects Antigravity and queries the local servers:
```bash
make test
```
This prints the JSON payload representing the current connection state, email, and quota buckets.
