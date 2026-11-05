# WAL sidecar files left by read-only reads

Reading a stage store read-only (`mode=ro`) may leave a `-wal` and a `-shm`
file next to it, such as `gold.db-wal` and `gold.db-shm`. The project accepts this. It does not try to
prevent read-only commands such as `status`, `review` and `serve` from
leaving those files.

## Why this is out of scope

Every stage store uses SQLite's write-ahead log (WAL) journal mode
(`PRAGMA journal_mode = WAL` in `src/budget/sqlstore.py`). In WAL mode SQLite
needs a `-wal` file and a `-shm` shared-memory index for every connection,
readers included, so a reader and a writer can work at the same time. A
read-only connection can create these files but cannot remove them. The next
read-write connection to close checkpoints the log and deletes them. SQLite
owns these files, and they don't change what the store holds. The test for
#419 checks that the main file's bytes are unchanged and the log is empty.

The ways to avoid the files are all worse:

- **`immutable=1`** tells SQLite that nothing else will change the file, so
  it skips locking and the WAL completely. That is safe only for files that
  really never change: backup sets and development's `upstream/` copies,
  which `open_store_snapshot` already opens this way. A live store can have a
  writer running beside it, and `status` must work while one is running
  (#296). An immutable reader there could read a torn or stale state without
  noticing.
- **Leaving WAL mode** (a rollback journal) blocks readers while a write is
  in progress. That gives up the concurrent reads WAL exists for (ADR-013).
- **Deleting the files ourselves** races with SQLite's own locking and could
  corrupt a store that a writer has open.

The files are harmless to the rest of the application. Backup, refresh and
restore already treat `-wal`, `-shm` and `-journal` as part of a store
(`_STORE_FILE_SUFFIXES` in `src/budget/restoring.py` and
`src/budget/refreshing.py`).

## Prior requests

- #422: "Decide whether read-only Gold reads may leave -wal and -shm sidecars"
