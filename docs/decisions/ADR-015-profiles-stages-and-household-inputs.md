# ADR-015: Separate Profiles, One Store per ETL Stage, and Household Inputs as Text

**Status:** Proposed

## Context

Issue #10 asks how the pipeline is operated at home: where data lives, how
production, development and test stay apart, how the household's own inputs
are kept, and how a build reaches the dashboard without a reader ever seeing
half of it. [ADR-013](ADR-013-sqlite-store-integer-minor-units.md) chose
SQLite, one writer at a time on one machine, and left the paths to #10.
[ADR-014](ADR-014-gold-publications-and-history.md), proposed in pull request
#57, defines what a Gold publication is and leaves the profile stores, command
names and file formats to #10.

Three requirements shape the answer:

- **Development/test/production separation is a learning objective** (issue
  #2). The pattern must carry to a workplace platform that has no test tier
  yet, so the three tiers stay distinct even where one household could manage
  with fewer.
- **Development diverges from a declared layer.** A Silver change rebuilds
  Silver and Gold from production Bronze; a Gold change rebuilds Gold from
  production Silver. Unchanged upstream layers are read, never recomputed or
  rewritten.
- **Production is written only by pipeline commands**, never by hand, an ad
  hoc SQL session, or a test.

The maintainer chose five things:

- stage each layer as its own store, following the extract, clean, conform,
  deliver steps of Kimball's ETL subsystems;
- development reads production only through production's latest backup;
- accounts, categories, rules and manual decisions live as text files in a
  folder, not in the database;
- configuration files are TOML;
- a Gold build is published as its own file behind a pointer, unless #8
  collides.

ADR-014 as drafted in #57 does collide. The maintainer left that choice open,
and this ADR takes one file per publication **on the agent's recommendation**;
see *Considered Options* and *Consequences*.

## Decision

- **Three profiles.** `production`, `development` and `test` are
  configurations of the same code, not three installations. A profile names
  every path the application touches. Nothing selects a profile implicitly: a
  command without `--profile` or `BUDGET_PROFILE` refuses to run. Test
  profiles are never files; the test suite builds each one in a temporary
  directory.
- **Every store knows its profile and stage.** `migrate` writes both into the
  store when it creates it. Opening a store under another profile, or as
  another stage, is refused. A test therefore cannot open a production store
  even when handed its path.
- **One SQLite store per ETL stage.** Each stage persists its output, so a
  failure restarts from the last completed stage, and the stores are the
  divergence points development needs.

  | Store | Kimball ETL step | Holds |
  | --- | --- | --- |
  | `bronze.db` | Extract | Raw payloads, import runs, source records |
  | `silver.db` | Clean and conform | Canonical transactions, quarantine, import review items |
  | `gold/catalog.db` | Deliver: control | Recipes, configuration snapshots, the pointer and its history, labels |
  | `gold/publication-<id>.db` | Deliver | One publication's Gold tables |

  Each store has its own numbered migrations and its own `PRAGMA
  user_version`.
- **One file per Gold publication.** A build writes a new publication file
  completely, then moves the pointer in `catalog.db` in one transaction. The
  pointer move is the commit point. A reader opens the file the pointer names,
  read-only, and a file holds exactly one publication.
- **Development reads production only through a backup set.** `dev refresh`
  restores production's latest backup set into development's read-only
  `upstream` folder. `rebuild --from <stage>` writes development's own stores
  from that stage onward and reads the stages before it from `upstream`.
  Development never opens a production store.
- **Household inputs are text.** The account registry, category taxonomy and
  classification rules are hand-edited TOML files. The decision log and the
  import log are append-only JSON Lines files, written only through the
  application's validation boundary, which the CLI uses now and a browser
  editor can reuse later. Bronze and the logs agree, so the stores can be
  rebuilt from the export archive and the inputs folder.

The paths, file formats, commands, walkthroughs, and the backup, restore and
access procedures are in
[`operations.md`](../architecture/operations.md).

## Considered Options

- **One database file for every stage** (ADR-013 as first written). Rejected:
  development would copy the whole file and overwrite its later stages, and
  nothing physical would stop the dashboard reading Silver.
- **Rows keyed by `publication_id` inside one Gold store** (ADR-014 as drafted).
  Rejected: every read then depends on a publication filter, and #57's own
  scenario shows a query without one reading 12,796.00 where the truth is
  3,349.00. A Gold migration would also have to convert or delete every
  retained result at once.
- **Replace `gold.db` by renaming a new file over it.** Rejected: Windows
  refuses to replace a file another process has open, and SQLite warns
  against renaming a database while it is in use.
- **Development attaches production's live stores read-only.** Rejected:
  production can change during a development run, and a long-lived reader
  keeps production's WAL file from resetting. Reading a backup set also
  rehearses a restore every time.
- **Manual decisions as rows in `bronze.db`.** Rejected: a development
  experiment could not add a decision without a separate overlay, and
  the decisions would not be readable or diffable as text.
- **A default profile.** Rejected: the default would be production, which is
  what a test run inherits from the operator's shell.

## Consequences

- **Refines ADR-013's location decision.** ADR-013 names "the database path";
  a profile now names one path per store. Everything else in ADR-013 applies
  to every store unchanged: `STRICT` tables, WAL mode, connection settings,
  integer minor units, the version floor, and backups through the backup API.
- **Collides with ADR-014 as drafted in #57.** Its rejected option *One
  database file per publication* must become the decision. `publication_id`
  stays the name of a publication and is still increasing. The retained
  results become retained files. A Gold migration no longer forces
  conversion: an older publication file keeps its schema version, and the
  running code refuses to open it and names the code version that can. If the
  maintainer keeps ADR-014 as drafted, the publication section of
  `operations.md` changes and the rest of this ADR stands.
- A write to Silver and a write to Gold are separate transactions. Readers see
  only Gold through the pointer, so a crash between them leaves the previous
  publication current, and the next command resumes.
- A publication file written by a crashed build has no catalog entry. The next
  command deletes it. A retained file that Windows refuses to delete, because
  the dashboard has it open, is deleted by a later command.
- The inputs folder is an input to every build, so a change to it is a change
  to a recipe. Hand edits to either log are detected. Every recipe records the
  hash of the decision-log prefix it read, and `verify` compares the import
  log with Bronze.
- Pull request #45's Bronze store opens and creates tables in one step. It
  must move its schema into the Bronze migrations and record its profile and
  stage.
- Resolves the operating-stack and profile parts of
  [issue #10](https://github.com/ATherkel/budget/issues/10) once accepted.
