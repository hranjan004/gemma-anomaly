"""Bounded AnyLog evidence functions.

Every quirk encoded here was confirmed against a live operator node. See
docs/ANYLOG_NOTES.md for the full write-up. Do not replace this transport with
requests or httpx.

  - No destination header. An empty body comes back when destination=network is
    set, because the blockchain advertises the operator on 127.0.0.1 and the
    hairpin never resolves.
  - Query partition tables directly. Parent table queries return empty.
  - Raw socket. AnyLog emits standalone hex chunk size markers that Python's
    chunked decoder rejects.
  - Never put a parenthesized channel name in a WHERE clause. It silently
    returns empty. Fetch the window and filter in Python.
  - State columns may hold 'on' / 'off' strings rather than integers. Read
    the schema rather than assuming.

There is no free form command surface here on purpose. Agents never reach the
database. They receive a built snapshot.
"""
from __future__ import annotations

import json
import logging
import re
import socket
from datetime import datetime, timedelta

from ..settings import anylog_host, anylog_port, site

log = logging.getLogger(__name__)

USER_AGENT = "AnyLog/1.23"
_PARTITION_CACHE: dict[str, list[tuple[str, datetime, datetime]]] = {}


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

def _request(command: str, timeout: int = 25) -> str:
    host, port = anylog_host(), anylog_port()
    headers = {
        "Host": f"{host}:{port}",
        "User-Agent": USER_AGENT,
        "Connection": "close",
        "command": command,
    }
    hdr = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    payload = f"GET / HTTP/1.1\r\n{hdr}\r\n".encode()

    sock = socket.create_connection((host, port), timeout=timeout)
    buf = b""
    try:
        sock.sendall(payload)
        sock.settimeout(timeout)
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    finally:
        sock.close()

    body = buf.split(b"\r\n\r\n", 1)[-1].decode(errors="replace")
    return re.sub(r"(?m)^[0-9a-fA-F]+\r?\n", "", body).strip()


def sql(statement: str, timeout: int = 30) -> list[dict]:
    """Run one local SQL statement. Returns [] on any failure."""
    dbms = site()["anylog"]["dbms"]
    raw = _request(f'sql {dbms} format=json and stat=false "{statement}"', timeout=timeout)
    if not raw or "Empty data set" in raw:
        return []
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("non-JSON reply for %.90s -> %.120s", statement, raw)
        return []
    if isinstance(body, dict):
        if "err_code" in body:
            log.warning("AnyLog error %s for %.90s", body.get("err_text"), statement)
            return []
        body = body.get("Query", [])
    return body if isinstance(body, list) else []


def admin(command: str, timeout: int = 15) -> str:
    return _request(command, timeout=timeout)


def health() -> dict:
    status = admin("get status")
    dbs = admin("get databases")
    return {
        "reachable": bool(status),
        "host": f"{anylog_host()}:{anylog_port()}",
        "databases_ok": site()["anylog"]["dbms"] in dbs,
        "status": status[:200],
    }


# --------------------------------------------------------------------------
# partitions
# --------------------------------------------------------------------------

def _partitions(table: str) -> list[tuple[str, datetime, datetime]]:
    """Discover partition table names.

    `get partitions` returns the partitioning POLICY, not the table names, so
    the names come from the table listing instead.
    """
    if table in _PARTITION_CACHE:
        return _PARTITION_CACHE[table]
    raw = admin(f"get tables where dbms = {site()['anylog']['dbms']}")
    found: list[tuple[str, datetime, datetime]] = []
    for name in set(re.findall(rf"par_{table}_\d{{4}}_\d{{2}}[_a-z0-9]*", raw)):
        m = re.match(rf"par_{table}_(\d{{4}})_(\d{{2}})", name)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        # Naive, to match the naive timestamps AnyLog returns.
        start = datetime(year, month, 1)
        end = datetime(year + (month == 12), (month % 12) + 1, 1)
        found.append((name, start, end))
    found.sort(key=lambda x: x[1], reverse=True)
    _PARTITION_CACHE[table] = found
    return found


def partitions_for(table: str, start: datetime, end: datetime) -> list[str]:
    hits = [p for p, p0, p1 in _partitions(table) if p0 < end and p1 > start]
    if hits:
        return hits
    parts = _partitions(table)
    return [parts[0][0]] if parts else []


def invalidate_partition_cache() -> None:
    _PARTITION_CACHE.clear()


# --------------------------------------------------------------------------
# bounded evidence functions
# --------------------------------------------------------------------------

def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_panel_window(channels: list[str], start: datetime, end: datetime,
                     limit: int = 200_000) -> dict[str, list[dict]]:
    """Power samples for the named channels, bounded by [start, end).

    Channel names are never sent in a WHERE clause. The window is fetched whole
    and filtered here, which is the only pattern that returns rows for the
    parenthesized panel names.
    """
    table = site()["anylog"]["tables"]["power"]
    wanted = set(channels)
    out: dict[str, list[dict]] = {c: [] for c in channels}
    for part in partitions_for(table, start, end):
        rows = sql(
            f"select ts, nm, w, kwh from {part} "
            f"where ts >= '{_fmt(start)}' and ts < '{_fmt(end)}' "
            f"order by ts limit {limit}"
        )
        for r in rows:
            nm = r.get("nm")
            if nm in wanted:
                out[nm].append(r)
    for c in out:
        out[c].sort(key=lambda r: r["ts"])
    return out


def get_appliance_estimates(panel_channel: str, start: datetime, end: datetime,
                            limit: int = 50_000) -> list[dict]:
    """Rows from nilm_disaggregated for one panel, filtered client side."""
    table = site()["anylog"]["tables"]["appliance"]
    rows: list[dict] = []
    for part in partitions_for(table, start, end):
        rows += sql(
            f"select ts, circuit, appliance, state, confidence, avg_w, median_w, "
            f"std_w, window_start, window_end, window_n from {part} "
            f"where ts >= '{_fmt(start)}' and ts < '{_fmt(end)}' "
            f"order by ts limit {limit}"
        )
    rows = [r for r in rows if r.get("circuit") == panel_channel]
    rows.sort(key=lambda r: r["ts"])
    return rows


def get_solar_snapshot(start: datetime, end: datetime, limit: int = 20_000) -> list[dict]:
    table = site()["anylog"]["tables"]["solar"]
    rows: list[dict] = []
    for part in partitions_for(table, start, end):
        rows += sql(
            f"select ts, pv_power, battery_power, battery_soc, grid_power, "
            f"load_power, device_mode from {part} "
            f"where ts >= '{_fmt(start)}' and ts < '{_fmt(end)}' "
            f"order by ts limit {limit}"
        )
    rows.sort(key=lambda r: r["ts"])
    return rows


def get_data_quality(start: datetime, end: datetime) -> list[dict]:
    """Per table row counts and last timestamp inside the window."""
    out = []
    for key, table in site()["anylog"]["tables"].items():
        if key == "anomaly":
            continue
        counts, last = 0, None
        for part in partitions_for(table, start, end):
            rows = sql(
                f"select count(*) as n, max(ts) as last_ts from {part} "
                f"where ts >= '{_fmt(start)}' and ts < '{_fmt(end)}'"
            )
            if rows:
                counts += int(rows[0].get("n") or 0)
                lt = rows[0].get("last_ts")
                if lt and (last is None or lt > last):
                    last = lt
        out.append({"table": table, "rows": counts, "last_ts": last})
    return out


def latest_timestamp(table_key: str = "power") -> datetime | None:
    table = site()["anylog"]["tables"][table_key]
    parts = _partitions(table)
    if not parts:
        return None
    rows = sql(f"select max(ts) as last_ts from {parts[0][0]}")
    if not rows or not rows[0].get("last_ts"):
        return None
    return datetime.fromisoformat(str(rows[0]["last_ts"]).replace("Z", ""))


def default_window(minutes: int = 30, now: datetime | None = None
                   ) -> tuple[datetime, datetime]:
    end = now or (latest_timestamp("power") or datetime.now())
    return end - timedelta(minutes=minutes), end
