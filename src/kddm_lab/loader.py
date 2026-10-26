from __future__ import annotations

from pathlib import Path
from shutil import copy2
from typing import Iterable

import duckdb
import pandas as pd

RAW_TABLES: dict[str, dict[str, str]] = {
    "customers": {"customer_zip_code_prefix": "VARCHAR"},
    "orders": {},
    "order_items": {},
    "products": {},
    "sellers": {},
}


def project_root(start: Path | str | None = None) -> Path:
    """Return the repository root by walking upward from the current directory."""
    current = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return current


def _discover_dataset_root(root: Path | str | None = None) -> Path | None:
    """Find the extracted Olist dataset directory anywhere below the project root."""
    project_dir = project_root(root)
    matches = list(project_dir.rglob("olist_*_dataset.csv"))
    if not matches:
        return None
    return matches[0].parent


def ensure_source_csvs(root: Path | str | None = None) -> Path:
    """Copy the extracted CSVs into data/raw when they exist elsewhere in the repository."""
    project_dir, raw_dir, _ = ensure_data_dirs(root)
    if any(raw_dir.glob("olist_*_dataset.csv")):
        return raw_dir

    source_dir = _discover_dataset_root(project_dir)
    if source_dir is None:
        return raw_dir

    for csv_file in source_dir.glob("olist_*_dataset.csv"):
        copy2(csv_file, raw_dir / csv_file.name)
    return raw_dir


def ensure_data_dirs(root: Path | str | None = None) -> tuple[Path, Path, Path]:
    """Create the project data folders if they are missing."""
    project_dir = project_root(root)
    data_dir = project_dir / "data"
    raw_dir = data_dir / "raw"
    warehouse_dir = data_dir / "warehouse"
    raw_dir.mkdir(parents=True, exist_ok=True)
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    return project_dir, raw_dir, warehouse_dir


def csv_path(table: str, root: Path | str | None = None) -> Path:
    """Return the expected CSV file path for one source table."""
    _, raw_dir, _ = ensure_data_dirs(root)
    ensure_source_csvs(root)
    return raw_dir / f"olist_{table}_dataset.csv"


def check_source_files(tables: Iterable[str] | None = None, root: Path | str | None = None) -> None:
    """Raise an informative error if the expected raw CSV files are missing."""
    ensure_source_csvs(root)
    table_names = list(tables) if tables is not None else list(RAW_TABLES)
    missing = [csv_path(table, root) for table in table_names if not csv_path(table, root).exists()]
    if missing:
        details = "\n".join(f" - {path}" for path in missing)
        raise FileNotFoundError(f"Missing CSV files for Olist dataset:\n{details}")


def build_duckdb_connection(
    database_path: str | Path | None = None,
    root: Path | str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create or reuse the DuckDB database used by the assignment notebook."""
    _, _, warehouse_dir = ensure_data_dirs(root)
    if database_path is None:
        database_path = warehouse_dir / "ecommerce.duckdb"
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    return con


def load_olist_raw(
    con: duckdb.DuckDBPyConnection | None = None,
    root: Path | str | None = None,
    tables: dict[str, dict[str, str]] | None = None,
) -> dict[str, int]:
    """Load all Olist CSV files into the raw schema and return row counts."""
    if con is None:
        con = build_duckdb_connection(root=root)

    project_dir, raw_dir, _ = ensure_data_dirs(root)
    ensure_source_csvs(project_dir)
    table_map = tables or RAW_TABLES
    check_source_files(table_map, root=project_dir)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    row_counts: dict[str, int] = {}
    for table_name, column_types in table_map.items():
        target = f'raw."{table_name}"'
        csv_file = raw_dir / f"olist_{table_name}_dataset.csv"
        source = con.read_csv(str(csv_file), header=True, dtype=column_types or None)
        con.execute(f"DROP TABLE IF EXISTS {target}")
        source.to_table(target)
        row_counts[table_name] = con.execute(f"SELECT count(*) FROM {target}").fetchone()[0]
    return row_counts


def q(con: duckdb.DuckDBPyConnection, sql_str: str) -> pd.DataFrame:
    """Run a SQL query in DuckDB and return a pandas DataFrame."""
    return con.sql(sql_str).df()


if __name__ == "__main__":
    connection = build_duckdb_connection()
    print(load_olist_raw(connection))
