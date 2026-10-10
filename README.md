# mcp-csv-lab

A small, read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that lets an MCP host request a CSV quality summary. It returns aggregates instead of raw rows, but aggregates can reveal individual values in small files. It uses the [official Python SDK v2](https://github.com/modelcontextprotocol/python-sdk).

## What it does

One tool, `profile_csv(file_path)`, reports row and column counts, blank cells by column, exact duplicate rows, and numeric min/max/mean for fully numeric columns. The path must be relative to one directory that you configure. The server reads files only; it has no write tools.

## Quick start

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
MCP_CSV_ROOT="$PWD/examples" python server.py
```

The last command waits for an MCP client on standard input. To connect from a local MCP host, configure it to launch this repository's `.venv/bin/python` with the absolute path to `server.py`, and set `MCP_CSV_ROOT` to the absolute path of the allowed CSV directory. Example host configuration shape:

```json
{
  "mcpServers": {
    "csv-lab": {
      "command": "/absolute/path/to/mcp-csv-lab/.venv/bin/python",
      "args": ["/absolute/path/to/mcp-csv-lab/server.py"],
      "env": {"MCP_CSV_ROOT": "/absolute/path/to/allowed-csvs"}
    }
  }
}
```

Call `profile_csv` with `{"file_path":"people.csv"}` when using the sample directory. Response excerpt:

```json
{
  "file": "people.csv",
  "rows": 4,
  "columns": 3,
  "duplicate_rows": 1,
  "missing_by_column": {"name": 0, "score": 1, "team": 0},
  "numeric_columns": {"score": {"count": 3, "min": 10.0, "max": 20.0, "mean": 16.6667}}
}
```

Run tests, including an in-memory MCP client call:

```bash
python -m unittest discover -s tests -v
```

## Access and limits

- `MCP_CSV_ROOT` is required and must point to an existing directory. Absolute paths, `..`, and symlinks escaping that root are rejected.
- Only existing `.csv` files are accepted. The default size cap is 2 MiB; set `MCP_CSV_MAX_BYTES` to an integer byte limit up to 20 MiB.
- Files must be UTF-8 (a UTF-8 BOM is accepted). Empty or whitespace-only cells count as missing; `NA` and `null` are text.
- The report includes column names and aggregate values. This is not an anonymization boundary: a one-row numeric CSV reveals that row's value through min, max, and mean. Do not connect it to a directory containing data you would not want your MCP host to see.
- A fully numeric column must have finite values in every nonblank cell. Mean is rounded to four decimals. The server does not infer business meaning or repair data.
- The file is loaded into memory up to the size cap; duplicates are tracked in memory. This is designed for small local CSVs.

## License

MIT. See [LICENSE](LICENSE).
