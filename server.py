"""A read-only MCP tool for profiling CSV files beneath one configured root."""

from __future__ import annotations

import csv
import io
import math
import os
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError


DEFAULT_MAX_BYTES = 2 * 1024 * 1024
HARD_MAX_BYTES = 20 * 1024 * 1024


class CSVLabError(ValueError):
    """An expected input or file access error."""


def _root_path(root: str | Path) -> Path:
    try:
        resolved = Path(root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CSVLabError("CSV root is unavailable") from exc
    if not resolved.is_dir():
        raise CSVLabError("CSV root must be a directory")
    return resolved


def _csv_path(root: Path, relative_path: str) -> Path:
    if not relative_path or "\x00" in relative_path:
        raise CSVLabError("file_path must be a nonblank relative CSV path")
    supplied = Path(relative_path)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise CSVLabError("file_path must stay inside the configured CSV root")
    try:
        resolved = (root / supplied).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CSVLabError("CSV file is unavailable") from exc
    if not resolved.is_relative_to(root):
        raise CSVLabError("file_path must stay inside the configured CSV root")
    if resolved.suffix.lower() != ".csv" or not resolved.is_file():
        raise CSVLabError("file_path must name an existing .csv file")
    return resolved


def profile_file(root: Path, relative_path: str, max_bytes: int) -> dict:
    """Return aggregate CSV health metrics without returning row contents."""
    root = _root_path(root)
    path = _csv_path(root, relative_path)
    try:
        if path.stat().st_size > max_bytes:
            raise CSVLabError(f"CSV exceeds {max_bytes} byte limit")
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise CSVLabError(f"CSV exceeds {max_bytes} byte limit")
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, None)
        if not headers:
            raise CSVLabError("CSV must have a header row")
        if any(not header.strip() for header in headers) or len(set(headers)) != len(headers):
            raise CSVLabError("CSV headers must be unique and nonblank")

        missing = {header: 0 for header in headers}
        numbers: dict[str, list[float]] = {header: [] for header in headers}
        numeric = {header: True for header in headers}
        seen: set[tuple[str, ...]] = set()
        duplicates = 0
        rows = 0
        for row in reader:
            if len(row) != len(headers):
                raise CSVLabError(
                    f"record {rows + 1} has {len(row)} cells; expected {len(headers)}"
                )
            rows += 1
            key = tuple(row)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
            for header, value in zip(headers, row):
                if not value.strip():
                    missing[header] += 1
                    continue
                if numeric[header]:
                    try:
                        parsed = float(value.strip())
                    except ValueError:
                        numeric[header] = False
                    else:
                        if math.isfinite(parsed):
                            numbers[header].append(parsed)
                        else:
                            numeric[header] = False
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CSVLabError("Could not read CSV") from exc

    stats = {}
    for header in headers:
        values = numbers[header]
        if numeric[header] and values:
            stats[header] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": round(math.fsum(value / len(values) for value in values), 4),
            }
    return {
        "file": str(path.relative_to(root)),
        "rows": rows,
        "columns": len(headers),
        "duplicate_rows": duplicates,
        "missing_by_column": missing,
        "numeric_columns": stats,
    }


def create_server(root: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> MCPServer:
    """Configure an MCP server with exactly one read-only tool."""
    resolved_root = _root_path(root)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= HARD_MAX_BYTES:
        raise CSVLabError(f"max_bytes must be between 1 and {HARD_MAX_BYTES}")

    server = MCPServer("mcp-csv-lab")

    @server.tool()
    def profile_csv(file_path: str) -> dict:
        """Profile a UTF-8 CSV under the configured root; return aggregates only."""
        try:
            return profile_file(resolved_root, file_path, max_bytes)
        except CSVLabError as exc:
            raise ToolError(str(exc)) from exc

    return server


def main() -> int:
    root = os.environ.get("MCP_CSV_ROOT")
    if not root:
        print("mcp-csv-lab: set MCP_CSV_ROOT to an existing directory", file=sys.stderr)
        return 2
    try:
        max_bytes = int(os.environ.get("MCP_CSV_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
        server = create_server(root, max_bytes)
    except (ValueError, CSVLabError) as exc:
        print(f"mcp-csv-lab: {exc}", file=sys.stderr)
        return 2
    server.run()  # stdio transport; stdout is reserved for MCP messages
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
