from __future__ import annotations

from typing import Iterable

import duckdb
import pandas as pd

from .loader import build_duckdb_connection, check_source_files, load_olist_raw


def _schema_name(schema: str) -> str:
    return schema.strip('"')


def build_star_schema(
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "warehouse",
) -> dict[str, int]:
    """Create a star schema in the target schema from the raw Olist tables."""
    if con is None:
        con = build_duckdb_connection()

    schema_name = _schema_name(schema)
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

    # Ensure raw datasets exist and are loaded.
    check_source_files()
    load_olist_raw(con)

    con.execute(f'DROP TABLE IF EXISTS "{schema_name}"."dim_customers"')
    con.execute(f'''
        CREATE TABLE "{schema_name}"."dim_customers" AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY customer_id) AS customer_key,
            customer_id,
            customer_unique_id,
            customer_zip_code_prefix,
            customer_city,
            customer_state
        FROM (
            SELECT DISTINCT
                customer_id,
                customer_unique_id,
                customer_zip_code_prefix,
                customer_city,
                customer_state
            FROM raw.customers
            WHERE customer_id IS NOT NULL
        ) d
    ''')

    con.execute(f'DROP TABLE IF EXISTS "{schema_name}"."dim_products"')
    con.execute(f'''
        CREATE TABLE "{schema_name}"."dim_products" AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY product_id) AS product_key,
            product_id,
            product_category_name,
            product_name_lenght,
            product_description_lenght,
            product_photos_qty,
            product_weight_g,
            product_length_cm,
            product_height_cm,
            product_width_cm
        FROM (
            SELECT DISTINCT
                product_id,
                product_category_name,
                product_name_lenght,
                product_description_lenght,
                product_photos_qty,
                product_weight_g,
                product_length_cm,
                product_height_cm,
                product_width_cm
            FROM raw.products
            WHERE product_id IS NOT NULL
        ) d
    ''')

    con.execute(f'DROP TABLE IF EXISTS "{schema_name}"."dim_sellers"')
    con.execute(f'''
        CREATE TABLE "{schema_name}"."dim_sellers" AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY seller_id) AS seller_key,
            seller_id,
            seller_zip_code_prefix,
            seller_city,
            seller_state
        FROM (
            SELECT DISTINCT
                seller_id,
                seller_zip_code_prefix,
                seller_city,
                seller_state
            FROM raw.sellers
            WHERE seller_id IS NOT NULL
        ) d
    ''')

    con.execute(f'DROP TABLE IF EXISTS "{schema_name}"."dim_dates"')
    con.execute(f'''
        CREATE TABLE "{schema_name}"."dim_dates" AS
        WITH source_dates AS (
            SELECT DISTINCT CAST(order_purchase_timestamp AS DATE) AS full_date
            FROM raw.orders
            WHERE order_purchase_timestamp IS NOT NULL
            UNION
            SELECT DISTINCT CAST(order_delivered_customer_date AS DATE) AS full_date
            FROM raw.orders
            WHERE order_delivered_customer_date IS NOT NULL
        )
        SELECT
            CAST(strftime(full_date, '%Y%m%d') AS BIGINT) AS date_key,
            full_date,
            EXTRACT(YEAR FROM full_date) AS year,
            EXTRACT(MONTH FROM full_date) AS month,
            EXTRACT(DAY FROM full_date) AS day,
            EXTRACT(QUARTER FROM full_date) AS quarter,
            CAST(DATE_PART('isodow', full_date) AS INTEGER) AS day_of_week,
            CASE WHEN CAST(DATE_PART('isodow', full_date) AS INTEGER) IN (6, 7) THEN 1 ELSE 0 END AS is_weekend
        FROM source_dates
        ORDER BY full_date
    ''')

    con.execute(f'DROP TABLE IF EXISTS "{schema_name}"."fact_order_items"')
    con.execute(f'''
        CREATE TABLE "{schema_name}"."fact_order_items" AS
        WITH item_base AS (
            SELECT
                o.order_id,
                o.order_status,
                o.customer_id,
                CAST(o.order_purchase_timestamp AS DATE) AS purchase_date,
                oi.order_item_id,
                oi.product_id,
                oi.seller_id,
                oi.price,
                oi.freight_value
            FROM raw.order_items oi
            LEFT JOIN raw.orders o USING (order_id)
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY order_id, order_item_id) AS order_item_key,
            c.customer_key,
            p.product_key,
            s.seller_key,
            d.date_key,
            ib.order_id,
            ib.order_status,
            ib.order_item_id,
            ib.product_id,
            ib.seller_id,
            ib.customer_id,
            ib.price,
            ib.freight_value,
            ib.price + ib.freight_value AS total_value
        FROM item_base ib
        LEFT JOIN "{schema_name}"."dim_customers" c
            ON c.customer_id = ib.customer_id
        LEFT JOIN "{schema_name}"."dim_products" p
            ON p.product_id = ib.product_id
        LEFT JOIN "{schema_name}"."dim_sellers" s
            ON s.seller_id = ib.seller_id
        LEFT JOIN "{schema_name}"."dim_dates" d
            ON d.full_date = ib.purchase_date
    ''')

    row_counts = {
        "dim_customers": con.execute(f'SELECT count(*) FROM "{schema_name}"."dim_customers"').fetchone()[0],
        "dim_products": con.execute(f'SELECT count(*) FROM "{schema_name}"."dim_products"').fetchone()[0],
        "dim_sellers": con.execute(f'SELECT count(*) FROM "{schema_name}"."dim_sellers"').fetchone()[0],
        "dim_dates": con.execute(f'SELECT count(*) FROM "{schema_name}"."dim_dates"').fetchone()[0],
        "fact_order_items": con.execute(f'SELECT count(*) FROM "{schema_name}"."fact_order_items"').fetchone()[0],
    }
    return row_counts


def validate_star_schema(
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "warehouse",
) -> pd.DataFrame:
    """Run a set of warehouse validation checks and return a summary DataFrame."""
    if con is None:
        con = build_duckdb_connection()

    schema_name = _schema_name(schema)
    checks = [
        (
            "fact_row_count_matches_raw_order_items",
            f'SELECT count(*) - (SELECT count(*) FROM raw.order_items) AS delta FROM "{schema_name}"."fact_order_items"',
        ),
        (
            "fact_null_customer_keys",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" WHERE customer_key IS NULL',
        ),
        (
            "fact_null_product_keys",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" WHERE product_key IS NULL',
        ),
        (
            "fact_null_seller_keys",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" WHERE seller_key IS NULL',
        ),
        (
            "fact_null_date_keys",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" WHERE date_key IS NULL',
        ),
        (
            "dim_customers_unique_keys",
            f'SELECT count(*) FROM (SELECT customer_key, COUNT(*) as n FROM "{schema_name}"."dim_customers" GROUP BY customer_key HAVING n > 1)',
        ),
        (
            "dim_products_unique_keys",
            f'SELECT count(*) FROM (SELECT product_key, COUNT(*) as n FROM "{schema_name}"."dim_products" GROUP BY product_key HAVING n > 1)',
        ),
        (
            "dim_sellers_unique_keys",
            f'SELECT count(*) FROM (SELECT seller_key, COUNT(*) as n FROM "{schema_name}"."dim_sellers" GROUP BY seller_key HAVING n > 1)',
        ),
        (
            "dim_dates_unique_keys",
            f'SELECT count(*) FROM (SELECT date_key, COUNT(*) as n FROM "{schema_name}"."dim_dates" GROUP BY date_key HAVING n > 1)',
        ),
        (
            "fact_unique_order_item_grain",
            f'SELECT count(*) FROM (SELECT order_id, order_item_id, COUNT(*) as n FROM "{schema_name}"."fact_order_items" GROUP BY order_id, order_item_id HAVING n > 1)',
        ),
        (
            "orphan_orders_in_fact",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" f LEFT JOIN raw.orders o ON o.order_id = f.order_id WHERE o.order_id IS NULL',
        ),
        (
            "orphan_customers_in_fact",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" f LEFT JOIN "{schema_name}"."dim_customers" dc ON dc.customer_key = f.customer_key WHERE dc.customer_key IS NULL',
        ),
        (
            "orphan_products_in_fact",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" f LEFT JOIN "{schema_name}"."dim_products" dp ON dp.product_key = f.product_key WHERE dp.product_key IS NULL',
        ),
        (
            "orphan_sellers_in_fact",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" f LEFT JOIN "{schema_name}"."dim_sellers" ds ON ds.seller_key = f.seller_key WHERE ds.seller_key IS NULL',
        ),
        (
            "orphan_dates_in_fact",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" f LEFT JOIN "{schema_name}"."dim_dates" dd ON dd.date_key = f.date_key WHERE dd.date_key IS NULL',
        ),
        (
            "total_value_calculation_mismatches",
            f'SELECT count(*) FROM "{schema_name}"."fact_order_items" WHERE abs(total_value - (price + freight_value)) > 0.000001',
        ),
        (
            "price_total_difference_from_raw",
            f'SELECT abs((SELECT sum(price) FROM "{schema_name}"."fact_order_items") - (SELECT sum(price) FROM raw.order_items))',
        ),
        (
            "freight_total_difference_from_raw",
            f'SELECT abs((SELECT sum(freight_value) FROM "{schema_name}"."fact_order_items") - (SELECT sum(freight_value) FROM raw.order_items))',
        ),
    ]
    rows = []
    for name, query in checks:
        value = con.execute(query).fetchone()[0]
        rows.append({"check_name": name, "result": value})
    return pd.DataFrame(rows)


def build_and_validate_star_schema(
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "warehouse",
) -> tuple[dict[str, int], pd.DataFrame]:
    """Convenience function to build the warehouse and return row counts plus validation summary."""
    row_counts = build_star_schema(con=con, schema=schema)
    validation = validate_star_schema(con=con, schema=schema)
    return row_counts, validation


if __name__ == "__main__":
    connection = build_duckdb_connection()
    row_counts, validation = build_and_validate_star_schema(connection)
    print("Warehouse row counts:")
    print(row_counts)
    print("\nValidation summary:")
    print(validation.to_string(index=False))
