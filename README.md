# rom-datatables

Turns the datatables that rom-tools decodes from the **ROM: Golden Age** client
into the **datapack** that rom-server loads. Only the fields the server needs
are kept, and they are renamed to server names. When rom-tools renames an
obfuscated client field, only the schema here changes. The server's Go structs
stay the same.

This repo only processes data. It selects and renames fields and nothing else:
every source row goes into the datapack, and no value is filtered, derived or
filled in here. Decisions about which rows a system uses belong to the server.

```
source/    rom-tools output (untracked)     tables/<Table>.json, {key: row}
schema/    one <entity>.toml per entity     which source fields, under which names
datapack/  what rom-server loads            <entity>.json + version.json (committed)
explore/   source/ as SQLite (untracked)    for browsing it in Datasette
```

## Usage

```bash
# once: point source/ at rom-tools' datatables output (or copy it in)
ln -sfn ../rom-tools/resources/datatables source

uv run rom-datatables build                 # source/ -> datapack/, reads datapack.toml
uv run rom-datatables build --pending       # ... and list source fields not yet in a schema
uv run rom-datatables explore               # browse source/ at http://127.0.0.1:8001
uv run rom-datatables --config other.toml build
```

`build` exports only what `schema/*.toml` lists: a field rom-tools newly confirms
doesn't reach the datapack until you add it. `--pending` lists, per entity, the
fields of its source table that pass the naming check but aren't in the schema,
with their type. Fields `schema.json` has but the decoded table lacks are
marked: rom-tools has to fix those before a schema can use them.

```
map: 5 Map_Data fields not in schema/map.toml
  scene.dataBundle                 string          (missing from tables/: fix in rom-tools)
  limit.userClass                  int32
  crystalIcon                      string
```

To produce `source/`, run `python3 -m datatables decode` in rom-tools (see
`rom-tools/client/datatables/README.md`).

## Configuration: [`datapack.toml`](datapack.toml)

| Key | |
|---|---|
| `[paths].source` | rom-tools' `resources/datatables/`. `tables/<Table>.json` and `schema.json` are read |
| `[paths].schema` | directory of entity schemas |
| `[paths].output` | where the datapack is written |
| `[paths].explore` | where `explore` keeps its database and Datasette metadata |
| `[meta].client_release` | client build the datapack came from, stamped into `version.json` |
| `[meta].schema_version` | bump when an entity's output fields change shape |

## Exploring the source: `explore`

`explore` loads `source/` into SQLite and serves it with
[Datasette](https://docs.datasette.io/), bound to `127.0.0.1` only. This is the
full client data dump: keep it on your machine, never deploy or publish it.

- One table per `source/tables/*.json`, keyed by `_key` (the row's key in the
  JSON). Nested objects become dot-path columns (`mapSize.width`,
  `limit.levelMin`), the same paths `schema/*.toml` uses. Lists are stored as
  JSON text; filter them in SQL with `json_each`. Booleans show as `1`/`0`.
- Each column's description (in its column menu) shows the naming status, type,
  obfuscated field id, referenced table and enum members, from `schema.json`.
  Use it to see which fields a schema can take.
- Columns that `schema.json` marks as referencing another table are foreign
  keys, so Datasette links each value to the referenced row.
- From Datasette itself: per-column filters, sorting, facets (e.g. rows per
  `mapType`), SQL queries across tables, and CSV/JSON export.

The database is rebuilt when any file in `source/` is newer than it (a few
seconds), or with `--rebuild`. `--port` picks another port.

## Entity schema: `schema/<entity>.toml`

The file name is the entity name. The output file is `datapack/<entity>.json`.

```toml
source = "Map_Data"        # source/tables/Map_Data.json
key = "id"                 # top-level output field, unique across rows

[fields]                   # output field -> dot-path into the source row
id = "index"
type = "mapType"

[fields.map_size]          # sub-table -> nested object, following the source
width = "mapSize.width"
height = "mapSize.height"
```

`source`, `key` and `fields` are the only keys a schema has. Any other key
fails the load.

Output fields keep the source's nesting (`mapSize: {width, height}` becomes
`map_size: {width, height}`) but use server names. A dot-path that points at an
object copies it whole, inner field names included.

## Naming check

rom-tools' `schema.json` gives each column a `naming` status. Before anything is
written, every dot-path in every schema is checked against it:

| `naming` | |
|---|---|
| `confirmed` | reviewed in rom-tools' `names.toml`. Allowed |
| `plaintext` | never obfuscated (`x`, `y`, `z`). Allowed |
| `tentative`, `suggested` | a name that may still be wrong. Rejected |
| `obfuscated` | no name yet, and it changes every client build. Rejected |

Every segment of a path must be allowed. A path that copies an object
(`limit = "limit"`) also needs every column inside it to be allowed, so list the
leaf fields when some of them aren't. The build fails listing every offending
path at once:

```
error: schema uses fields whose naming is not confirmed, plaintext:
  [map] 'capacity': 'capacity' is tentative (field CAIEKGMKOJM)
  [map] 'limit' copies 'limit.FFIEBMMLAOC', which is obfuscated (field FFIEBMMLAOC)
```

To use such a field, confirm its name in rom-tools first.

## Output

- `<entity>.json`: a JSON array of the projected rows, in ascending source key
  order.
- `version.json`: `client_release`, `schema_version`, and for each entity its
  source table, row count and the type of each field.

Field types come from the column's metadata in `source/schema.json` and follow
the shape of the output:

```json
"fields": {
  "id": {"type": "int32"},
  "type": {"type": "enum", "values": ["MT_NONE", "MT_METROPOLIS", "..."]},
  "map_buffs": {"type": "list", "items": {"type": "int32"}},
  "map_size": {"type": "object", "fields": {"width": {"type": "int32"}, "...": {}}}
}
```

Scalars are `bool`, `int32`, `uint32`, `int64`, `float32`, `float64` and
`string`. An `enum` lists its members in value order. rom-tools writes a
declared value as its member name, a combination of single-bit members as
`A|B`, and any other value as the plain number. A column type the tool can't
map fails the build.

The output is deterministic, with no timestamps, so a diff of `datapack/` shows
exactly what a new client build or schema edit changed.

The build fails fast and writes nothing further when it hits a missing source
table, a path that fails the naming check, a missing source path in any row, or
a duplicate key. Each of these means the schema or the rom-tools output is wrong.

## Development

```bash
uv sync                                     # dev + explore (Datasette) groups
uv run ruff format src tests && uv run ruff check src tests
uv run mypy
uv run pytest
```
