# KDDM Lab

This project sets up an Olist e-commerce data warehouse assignment with DuckDB and Python.

## What is included

- A Python package at `src/kddm_lab` with project utilities for file discovery and DuckDB setup
- A reusable loader for the source Olist CSV files
- A `data/` folder layout for raw CSV inputs and the local DuckDB warehouse
- A notebook scaffold for the assignment work at `DWH_OLAP_Assignment_1_Notebook.ipynb`

## Expected source data layout

Place the source CSVs in:

- `data/raw/olist_customers_dataset.csv`
- `data/raw/olist_orders_dataset.csv`
- `data/raw/olist_order_items_dataset.csv`
- `data/raw/olist_products_dataset.csv`
- `data/raw/olist_sellers_dataset.csv`

## Quick start

```bash
# from the project root
python -m kddm_lab
```

This creates the required folder structure and confirms the project is set up correctly.

## Loader usage

```python
from pathlib import Path
from kddm_lab.loader import build_duckdb_connection, load_olist_raw

con = build_duckdb_connection()
row_counts = load_olist_raw(con)
print(row_counts)
```

## Star schema ETL

```python
from kddm_lab.loader import build_duckdb_connection
from kddm_lab.warehouse import build_and_validate_star_schema

con = build_duckdb_connection()
row_counts, validation = build_and_validate_star_schema(con)
print(row_counts)
print(validation.to_string(index=False))
```

You can also run the ETL directly:

```bash
python -m kddm_lab.warehouse
```

## ERD summary

```mermaid
erDiagram
    customers ||--o{ orders : "places"
    orders ||--o{ order_items : "contains"
    products ||--o{ order_items : "included_in"
    sellers ||--o{ order_items : "fulfills"

    customers {
        varchar customer_id PK
        varchar customer_unique_id
        varchar customer_zip_code_prefix
        varchar customer_city
        varchar customer_state
    }

    orders {
        varchar order_id PK
        varchar customer_id FK
        varchar order_status
        timestamp order_purchase_timestamp
        timestamp order_approved_at
        timestamp order_delivered_carrier_date
        timestamp order_delivered_customer_date
        timestamp order_estimated_delivery_date
    }

    order_items {
        varchar order_id PK, FK
        integer order_item_id PK
        varchar product_id FK
        varchar seller_id FK
        timestamp shipping_limit_date
        double price
        double freight_value
    }

    products {
        varchar product_id PK
        varchar product_category_name
        integer product_name_lenght
        integer product_description_lenght
        integer product_photos_qty
        double product_weight_g
        double product_length_cm
        double product_height_cm
        double product_width_cm
    }

    sellers {
        varchar seller_id PK
        varchar seller_zip_code_prefix
        varchar seller_city
        varchar seller_state
    }
```
