# CurseForge integration

The integration uses the [official REST API documentation](https://docs.curseforge.com/rest-api/) and [official CDN authentication guidance](https://blog.curseforge.com/introducing-api-key-authentication-for-curseforge-file-downloads/).

## Current state

The catalog interface and server-side client are implemented. A real API key has not yet been approved or configured in the personal deployment. API behavior is tested with mocked responses; authenticated live catalog access and real CurseForge downloads remain to be verified after approval. No fake downloads or fabricated catalog statistics are shown.

Without credentials, the interface displays clearly labeled local project links. These are not cached API results. The complete catalog, categories, version listings, file downloads, and remote installation require a valid key.

## Configure after approval

Log into the server as the same account used for the Cockpit panel. Enter the key directly in that account's terminal, keeping it out of chat, command history, Git, browser URLs, and screenshots:

```bash
install -d -m 700 "$HOME/.config/carvalholinks"
umask 077
read -r -s -p 'CurseForge API key: ' carv_cf_key
printf '\n'
printf '%s' "$carv_cf_key" > "$HOME/.config/carvalholinks/curseforge.key"
unset carv_cf_key
chmod 600 "$HOME/.config/carvalholinks/curseforge.key"
```

The client rejects a key file readable by other accounts, a key owned by another user, and symbolic links on supported POSIX hosts. `CURSEFORGE_API_KEY` is an alternative for an appropriately configured process environment. The frontend never receives the key. No new key is generated and no agreement is accepted by this code.

Reload the panel and select **Conectar catálogo**. This checks game access and loads the categories and first search page. The game is discovered through `/v1/games` using the exact `minecraft-bedrock` slug, not an assumed numeric ID. Subsequent requests validate that the selected game and project belong to Bedrock. `CURSEFORGE_GAME_ID` can reduce discovery requests, but is still checked against the API's game metadata.

## Endpoints

- `GET /v1/games` and `GET /v1/games/{id}` — discover and validate Minecraft Bedrock.
- `GET /v1/categories?gameId=...` — filters.
- `GET /v1/mods/search` — search, category, declared game version, sorting, pagination.
- `GET /v1/mods/{id}` — project, authors, game, and distribution preference.
- `GET /v1/mods/{id}/files` — available versions and dependency metadata.
- `GET /v1/mods/{id}/files/{fileId}` — verify file ownership, availability, size, and hashes.
- `GET /v1/mods/{id}/files/{fileId}/download-url` — official authorized download resolution.

Catalog reads occur only on explicit user actions, not during the 15-second server-status refresh. There is no persistent catalog cache. Each operation has an API-call budget, bounded response sizes, and request timeouts. Errors such as 401, 403, and 429 produce actionable messages without exposing credentials.

## Download and installation

1. Select a file or a matching behavior/resource pack pair from one project.
2. Recheck project ownership, Bedrock game, author distribution preference, and file availability.
3. Resolve the URL through the official API. Never guess a CDN URL or bypass distribution restrictions.
4. Download over HTTPS from the official `*.forgecdn.net/files/` namespace with `x-api-key`. Redirects are checked before a credential is sent to the destination; off-domain redirects are rejected.
5. Verify announced size and API-provided SHA-1/MD5 checksum, and require a ZIP-based Bedrock package. This checks integrity, not whether the add-on is trustworthy.
6. **Baixar arquivo** transfers the validated file to the authenticated administrator's browser. **Instalar selecionados** reuses local archive, minimum-engine, dependency, offline backup, and rollback checks before changing the world.

Downloads and batches are limited to 16 MB. At most four files from the same project can be selected in a batch. `.jar`, world downloads, early-access files, and other unsupported formats are not automatically installed. Required dependencies on other projects are displayed and must be reviewed and installed separately; they are not silently downloaded. A future compatibility failure remains possible even when declared game versions and manifests match.

Before normal use with a new key, verify search, project images, version listings, a permitted download, a restricted project, and one installation on a copy of a world. No changes to a running game's transport or player data are needed to enable the catalog itself.
