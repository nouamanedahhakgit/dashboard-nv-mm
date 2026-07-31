"""Safe Nevis API connectivity diagnostic. Does not print the password."""

from __future__ import annotations

import configparser
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "nevis_api.ini"


def setting(config, section, option):
    return config.get(section, option, fallback="").strip()


def parse_table(payload):
    root = ET.fromstring(payload)
    table = root.find(".//data-table")
    if table is None:
        text = " ".join(value.strip() for value in root.itertext() if value.strip())
        raise RuntimeError(f"No data-table in XML response: {text[:300]}")
    columns = [
        (node.text or "").strip()
        for node in list(table.find("columns") or [])
    ]
    rows_node = table.find("rows")
    rows = list(rows_node) if rows_node is not None else []
    return table.attrib.get("count", str(len(rows))), columns, rows


def request(session, label, url, params):
    print(f"\n[{label}] Requesting API...")
    started = time.perf_counter()
    try:
        response = session.get(url, params=params, timeout=(5, 45))
    except requests.RequestException as exc:
        raise RuntimeError(f"{label} connection failed: {type(exc).__name__}: {exc}") from exc
    elapsed = time.perf_counter() - started
    print(f"[{label}] HTTP {response.status_code} in {elapsed:.2f}s")
    print(f"[{label}] Content-Type: {response.headers.get('Content-Type', 'not provided')}")
    if response.status_code == 401:
        raise RuntimeError("HTTP 401: Basic Auth username or password was rejected.")
    if response.status_code == 403:
        raise RuntimeError("HTTP 403: account is authenticated but not authorized for this query.")
    response.raise_for_status()
    try:
        count, columns, rows = parse_table(response.content)
    except Exception as exc:
        preview = response.text[:300].replace("\n", " ")
        raise RuntimeError(f"{label} returned invalid query XML. Preview: {preview}") from exc
    print(f"[{label}] Rows reported: {count}")
    print(f"[{label}] Columns: {len(columns)}")
    return columns, rows


def main():
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Configuration file not found: {CONFIG_PATH}")
    config = configparser.RawConfigParser()
    config.read(CONFIG_PATH, encoding="utf-8")
    unit_url = setting(config, "api", "unit_url")
    visit_url = setting(config, "api", "vessel_visit_url")
    phase = setting(config, "api", "phase") or "working"
    username = setting(config, "auth", "username")
    password = setting(config, "auth", "password")
    if not unit_url or not visit_url:
        raise RuntimeError("One or both API URLs are missing.")
    if not username or not password:
        raise RuntimeError("Username or password is empty in nevis_api.ini.")

    print(f"Config: {CONFIG_PATH}")
    print(f"Username configured: {username!r}")
    print(f"Password configured: yes ({len(password)} characters)")
    print(f"Phase: {phase!r}")

    with requests.Session() as session:
        # Connect directly to the internal Nevis host instead of inheriting
        # HTTP_PROXY/HTTPS_PROXY settings from Windows or the shell.
        session.trust_env = False
        session.auth = (username, password)
        session.headers.update(
            {
                "Accept": "application/xml, text/xml;q=0.9, */*;q=0.5",
                "Connection": "keep-alive",
                "User-Agent": "Nevis-Vessel-Command-Center/1.0",
            }
        )
        visit_columns, visit_rows = request(
            session, "VESSEL VISITS", visit_url, {"param_phase": phase}
        )
        if "Visit" not in visit_columns:
            raise RuntimeError("Vessel response does not contain the Visit column.")
        visit_index = visit_columns.index("Visit")
        visit_ids = []
        for row in visit_rows:
            fields = list(row)
            if visit_index < len(fields):
                visit_id = (fields[visit_index].text or "").strip()
                if len(visit_id) == 9 and visit_id.isdigit():
                    visit_ids.append(visit_id)
        if not visit_ids:
            raise RuntimeError("No numeric vessel visit was returned for this phase.")

        sample_visit = visit_ids[0]
        print(f"\nTesting Unit API with vessel visit {sample_visit}...")
        unit_columns, _ = request(
            session,
            "UNITS",
            unit_url,
            {
                "param_ibactualvisit": sample_visit,
                "param_obactualvisit": sample_visit,
            },
        )
        expected = {"Unit Nbr", "I/B Actual Visit", "O/B Actual Visit", "Last Move"}
        missing = sorted(expected.difference(unit_columns))
        if missing:
            raise RuntimeError(f"Unit response is missing required columns: {missing}")

    print("\nSUCCESS: Vessel Visit and Unit APIs are reachable, authenticated, and readable.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
