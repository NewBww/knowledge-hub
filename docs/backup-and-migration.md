# Backup, restore and migration

## Before an upgrade

1. Quit Knowledge Hub and disconnect/stop all MCP clients and other processes using the same data root. The app closing does not necessarily terminate an independently launched MCP server.
2. Copy the **whole selected data directory** to a private, protected backup location. Default: `~/Library/Application Support/Knowledge Hub`. Preserve captures, settings, migration backups and any SQLite sidecar files; do not copy only the main database from an active process.
3. Record the installed version and selected data root outside public issue reports. Keep the prior app separately if your policy allows, but do not assume it can open a newer schema.
4. Replace only the app. Never store knowledge inside the app bundle or source checkout.

A filesystem copy does not back up macOS Keychain items or guarantee portable official-client sessions. Do not export secrets casually. Plan to reauthenticate connections after a restore or move.

## Restore safely

With all users of the store stopped, keep the current directory intact as a separate recovery copy. Restore the complete backup to a separate private location, then launch a compatible app with an explicit `--data-dir <restored-directory>` for inspection. Check accepted records, Library pages, revisions and capture/access state before choosing it as your live root. Do not merge SQLite files manually or run two independently modified copies as though they synchronize.

## Migration boundaries

The store rejects databases newer than the supported schema. Shared-Warehouse migration and legacy scoped-permission handling are application behavior, not a promise of arbitrary downgrade compatibility. A historical backup file is not proof that every side resource migrated atomically. Release acceptance must test upgrade from the supported previous version and backup recovery with synthetic data.

If startup reports a newer schema or migration failure: stop, preserve both app versions and data copies, and ask for guidance with a sanitized error. Do not lower SQLite schema numbers or force old code to open it. This app is not a cloud sync/merge service, and direct database edits bypass revision and approval rules.

See [store migrations](../src/knowledge_hub/store.py), [shared-Warehouse migration](../src/knowledge_hub/shared.py) and [release checklist](releasing.md).
