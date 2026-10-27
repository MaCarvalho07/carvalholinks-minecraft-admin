# CarvalhoLinks Minecraft Admin

A personal, self-hosted administration dashboard for a Minecraft Bedrock Dedicated Server, integrated into the CarvalhoLinks homelab hub and authenticated through Cockpit.

This repository contains the first working version of the dashboard and its read-only in-game telemetry bridge. The interface is currently in Brazilian Portuguese. This is a small personal project for learning and managing a server played on with friends, with no current monetization plans.

## Current features

- Server state, health, CPU, memory, available disk space, and estimated tick rate (TPS).
- Private performance history: 15-second collection, 30-day retention, period filters, interactive charts, active-player TPS dip records, and CSV export. Collection continues without an open browser.
- Start, stop, and restart controls for an existing Docker container.
- Online players, health, hunger, position, dimension, and game mode.
- Read-only inventory and equipment inspection, including available durability and enchantment information.
- Local `.mcaddon` and `.mcpack` uploads, pack activation, dependency checks, and minimum-engine version validation.
- CurseForge catalog UI with search, categories, author attribution, project cards, paginated files, server-side downloads, and installation (API key required).
- Offline, consistent backups before add-on changes and restores, with SHA-256 verification.
- Backup download and restoration, retaining the current server runtime version.
- Local operation audit log and explicit confirmation dialogs for world-changing actions.

## CurseForge integration — implementation ready, credentials pending

**The API client and interface are implemented. API access is being requested; live authenticated catalog and download checks are pending key approval.**

The integration allows the administrator to search Minecraft Bedrock add-ons and resource packs, inspect author and project details, review available versions, and download author-authorized files for installation on the administrator's own server. Before a key is configured, the interface explicitly shows a small local selection of official project links, rather than presenting it as live API search results.

The project is not intended to mirror the CurseForge catalog or operate a public file redistribution service. The integration preserves author attribution and links to original project pages, respects third-party distribution permissions, and uses official authorized download mechanisms. If a project does not permit third-party downloads, the administrator is directed to its official page. No API key is included in this repository. See [CURSEFORGE.md](CURSEFORGE.md) for setup and verification limits.

Supported game: **Minecraft: Bedrock Edition**. Minecraft Java Edition, Forge `.jar` mods, and commercial distribution are outside the current scope.

## Architecture

```text
Public CarvalhoLinks hub
        |
        +-- Link to private administration
                       |
               Cockpit authenticated session
                       |
                 cockpit.spawn()
                       |
                 Local Python backend
                   /           \
           Docker controls    World / pack / backup files
                  |
        Bedrock read-only telemetry bridge
        (health, hunger, inventory -> local console logs)
```

The backend has no HTTP listener. Public monitoring and administrative controls are separate. The Bedrock script has no network API dependency and does not modify player inventories. The administrator's existing server account must already have the necessary filesystem and Docker permissions.

## Source layout

| File | Purpose |
| --- | --- |
| `index.html`, `style.css`, `app.js` | Cockpit administration interface |
| `manifest.json` | Cockpit package registration |
| `admin.py` | Local operations, validation, snapshots, backups, and audit log |
| `bridge.js` | Read-only Bedrock Script API telemetry |
| `bridge-manifest.json` | Manifest for the Bedrock behavior pack |
| `test_admin.py` | Safety, archive, telemetry, backup, and restoration tests |
| `curseforge.py` | Host-side official API client, restricted CDN download, checksum validation |
| `catalog.js`, `catalog.css` | Catalog interface and file selection dialog |
| `catalog.html`, `catalog-dialog.html` | Source fragments already assembled into `index.html` |
| `build_catalog.py` | Reassemble the catalog fragments after changing their markup |
| `test_curseforge.py` | Mocked API contract, permission, checksum, redirect, and credential handling tests |
| `history.py` | Numeric telemetry collection, private SQLite storage, retention, aggregation, and CSV export |
| `history.js`, `history.css`, `history.html` | Interactive performance timeline; HTML already assembled into `index.html` |
| `build_history.py` | Reassemble the history markup after editing it |
| `test_history.py`, `test_history_frontend.js` | History integrity, retention, privacy, missing readings, and chart-gap checks |

## Deployment notes

This is a source snapshot of a running personal deployment, rather than a general-purpose one-click installer. Deployment-specific installation scripts, server addresses, credentials, logs, player data, worlds, third-party add-ons, and backups are excluded.

The current source expects:

- A Linux host with Cockpit, Python 3.11+ with current security updates, and Docker CLI.
- An existing container named `minecraft-bedrock`.
- Game data at `~/minecraft-bedrock/data` and an existing `~/minecraft-bedrock/compose.yml`.
- Panel files installed at `~/minecraft-bedrock/admin`.
- A Cockpit package named `minecraftadmin`, usually linked from `~/.local/share/cockpit/minecraftadmin` to the panel directory.

Install the telemetry behavior pack using `bridge-manifest.json` as its `manifest.json` and `bridge.js` as `scripts/main.js`, after making a consistent backup and stopping the server. Register it in the world's `world_behavior_packs.json`. The bridge declares the stable `@minecraft/server` API version `2.8.0`; verify support in the target Bedrock release before activation.

The deployment must enable content logging to the server console and configure bounded Docker log rotation. The personal deployment uses three log files of 10 MB and disables duplicate content logging to unbounded disk files. Console telemetry includes player inventory information: keep logs private.

Open `/minecraftadmin` in the authenticated Cockpit session. Use the local network or a private VPN for administrative access. Keep the page open until maintenance operations finish. Test against a copy of a world before using it on another server.

## Validation and limitations

Run:

```sh
python3 -m unittest discover -p 'test_*.py'
node --check app.js
node --check bridge.js
node --check catalog.js
node --check history.js
node test_history_frontend.js
```

After editing catalog markup fragments, run `python3 build_catalog.py` before deploying `index.html`. This buildless UI uses the host's Cockpit JavaScript API and needs no npm dependencies.

After editing history markup, run `python3 build_history.py`. See [PERFORMANCE.md](PERFORMANCE.md) for collection scheduling, metrics, and retention. Install the collector separately from the browser UI; opening a dashboard is not what creates history samples.

The test suite covers ZIP path traversal, symbolic links, invalid archives, nested add-on archives, missing script entry points, pack dependencies, stale telemetry, backup checksums, and restoration into a temporary directory while preserving the runtime configuration.

The initial deployment has also been checked with a real connected player, confirming online status, health, hunger, position, and inventory readings. A backup was created through the dashboard and the server returned to a healthy state.

The bridge estimates TPS from elapsed wall-clock time and `system.currentTick` over 200-tick samples, capped at 20 TPS. This is a server tick-rate estimate, not a network latency measurement or a profiler. An idle world at 20 TPS does not establish that gameplay is smooth under load.

The known NetherNet startup banner is grouped into a collapsible transport diagnostic. It remains a warning until a player connection is observed in the current server run; under RakNet, an observed connection makes it informational. Original records remain intact, and unrelated or interleaved errors remain in the actionable error list. This changes dashboard classification, not the Minecraft binary or its log level. Moving an existing UDP-only tunnel to NetherNet requires a separate networking migration.

Current limits:

- Online players only; inventories are read-only.
- Uploads up to 16 MB; backup downloads through the UI up to 64 MB.
- Packages requesting experimental APIs or additional capabilities require manual review.
- Dependency and archive checks do not prove that an add-on is safe or compatible; use trusted sources and verify in-game behavior.
- A healthy process or successful ping does not, by itself, prove that a player can join. Transport warnings remain visible in diagnostics, alongside whether a player connection has actually been observed.
- No third-party add-on files or game assets are redistributed in this repository.

## Project website

[CarvalhoLinks public project hub](https://carvserver-1.tail5cf408.ts.net/inicio/)

Administrative controls require a private, authenticated server session and are not available through the public website.
