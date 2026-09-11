# AnyLog operational notes

Behaviors confirmed against a live [AnyLog](https://github.com/AnyLog-co/EdgeLake)
2.x deployment, operator node on the standard REST port. Each of these cost
real debugging time, and none of them is obvious from the documentation. They
are why `src/gemma_anomaly/evidence/anylog.py` looks the way it does.

## Use a raw socket, not an HTTP client

A SQL query issued with `curl`, `requests`, or `httpx` hangs and eventually
times out. The node emits standalone hex chunk-size lines that standard chunked
transfer decoders reject, so the client waits for a body it will never parse.

The working approach is a raw socket, read to EOF, split on the header
boundary, then strip lines matching `^[0-9a-fA-F]+\r?\n`. Administrative
commands such as `get status` return normally through any client; it is only
the SQL path that breaks.

## Omit the destination header for local SQL

`destination: network` returns HTTP 200 with an empty body, or an error object
with `err_code` 203 and `err_text` `Operator not available`.

The cause is that the blockchain ledger advertises the operator at its
container-local address. A routed lookup from outside resolves to something
unreachable. Sending the query to the operator's own REST port with no
destination header runs it locally and returns rows.

## Discover partitions from the table list, not from `get partitions`

`get partitions` returns the partitioning *policy*, for example
`customers.* : (1, 'month', 'insert_timestamp')`. It does not return partition
table names, so a discovery routine built on it silently finds nothing and
every downstream query returns an empty result.

Partition names come from `get tables where dbms = <name>`, which lists entries
of the form `par_<table>_<year>_<month>_<unit>_<column>`.

## Query partition tables directly

A query against the parent table returns empty. Resolve the partitions covering
your time range and query each one, then merge in Python.

## Never put a parenthesized channel name in a WHERE clause

A predicate such as `where nm = 'Panel1 (Climate)'` silently returns no rows.
Fetch the whole time window and filter client side. This also applies to `IN`
and `LIKE` against the same values.

## Check the column types before comparing

Boolean-looking state columns may hold strings rather than integers. A
recommender comparing `state == 1` against a column storing `'on'` and `'off'`
produces zero results and no error. Read the schema with
`get columns where dbms = <name> and table = <name>` rather than assuming.

## Streaming writes

A streaming `PUT` must exclude `insert_timestamp` from the payload; the node
fills it and routes to the correct partition from it. Timestamps carrying a
trailing `Z` cause coercion failures.

For a table to accept positional auto-fill, its schema needs `tsd_name CHAR(3)`
and `tsd_id INT` as columns three and four, after `row_id` and
`insert_timestamp`.

## Required header

`User-Agent: AnyLog/1.23` is required. Omitting it causes silent failures
rather than an error.
