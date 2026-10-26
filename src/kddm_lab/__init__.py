from .loader import (
    RAW_TABLES,
    build_duckdb_connection,
    check_source_files,
    ensure_data_dirs,
    load_olist_raw,
    project_root,
    q,
)

__all__ = [
    "RAW_TABLES",
    "build_duckdb_connection",
    "build_star_schema",
    "check_source_files",
    "ensure_data_dirs",
    "load_olist_raw",
    "project_root",
    "q",
    "validate_star_schema",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    if name in {"build_star_schema", "validate_star_schema"}:
        from .warehouse import build_star_schema, validate_star_schema

        return {
            "build_star_schema": build_star_schema,
            "validate_star_schema": validate_star_schema,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    root, raw_dir, warehouse_dir = ensure_data_dirs()
    print(f"kddm-lab ready at {root}")
    print(f"Raw data directory: {raw_dir}")
    print(f"Warehouse directory: {warehouse_dir}")
