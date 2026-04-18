# Ill-Formatted Join Key Mappings Across DAB Databases

## Yelp Dataset

**Default seeded `yelp_db` (Mongo)** contains **`business`** and **`checkin`** only. Per-review fields (`review_id`, `text`, `stars` / `rating`, `useful`) live in **PostgreSQL** and **DuckDB** (`review` tables), not in a Mongo `reviews` collection.

| Entity | PostgreSQL Format | MongoDB Format | Transformation |
| ------ | ---------------- | -------------- | -------------- |
| business_id | "abc123def456" (TEXT) | "abc123def456" (STRING) | Often direct match; **in some seeded SQL slices** the fact table’s foreign key column and the dimension table’s primary key use **different string prefixes** for the same entity (empty joins if you equate them literally). Compare sample values in schema metadata and **normalize** (e.g. common prefix swap) in the join predicate. DuckDB `review.business_ref` vs Postgres `business.business_id` may need the same care. |
| user_id | "user_12345" (TEXT) | *(no `user` collection in default dump)* | N/A for default seed — use Postgres `"user"` / DuckDB `user` |
| review_id | "xyz789abc123" (TEXT) | *(reviews not in Mongo by default)* | Use SQL/DuckDB for review rows |

## Telecom Dataset

| Entity | PostgreSQL Format | MongoDB Format | Transformation |
| ------ | ---------------- | -------------- | -------------- |
| subscriber_id | 1234567 (INT) | "CUST-1234567" (STRING) | f"CUST-{subscriber_id}" |
| ticket_id | "TKT-12345678" (TEXT) | "TKT-12345678" (STRING) | Direct match |

## Healthcare Dataset

| Entity | PostgreSQL Format | MongoDB Format | Transformation |
| ------ | ---------------- | -------------- | -------------- |
| patient_id | 987654321 (INT) | "PT-987654321" (STRING) | f"PT-{patient_id}" |
| provider_npi | 1234567890 (INT) | "NPI-1234567890" (STRING) | f"NPI-{provider_npi}" |

## Detection Logic

When a join fails, use `JoinKeyResolver` from `utils/join_key_resolver.py` to detect and fix the mismatch:

1. Check if one side is INT, other is STRING with prefix
2. Extract numeric part: `re.sub(r'\D', '', string_value)`
3. Compare numeric values
4. Apply correct transformation based on table name

## Code Implementation

```python
from utils.join_key_resolver import JoinKeyResolver

resolver = JoinKeyResolver()

# PostgreSQL INT → MongoDB STRING (Telecom: subscriber_id → "CUST-{id}")
def pg_to_mongo_telecom(pg_int_id: int) -> str:
    return f"CUST-{pg_int_id}"

# PostgreSQL INT → MongoDB STRING (Healthcare: patient_id → "PT-{id}")
def pg_to_mongo_healthcare(pg_int_id: int) -> str:
    return f"PT-{pg_int_id}"

# Generic cross-DB key resolution (auto-detects normalization needed)
pg_key, mongo_key = resolver.resolve_cross_db_join(
    left_key=subscriber_id,
    right_key=mongo_ref,
    left_db_type='postgresql',
    right_db_type='mongodb'
)

def transform_yelp_user_id(user_id: str) -> str:
    """Idempotent: safe to call even if already in USER- format."""
    if user_id.startswith('USER-'):
        return user_id  # already transformed — do not double-transform
    return user_id.replace('user_', 'USER-')
```

## PANCANCER_ATLAS Dataset (M5)

Live files (see `duckdb_schemas.md`, `postgresql_schemas.md`):

- **DuckDB** `pancancer_molecular.db`: tables **`Mutation_Data`** and **`RNASeq_Expression`** use **`ParticipantBarcode`** (e.g. `TCGA-AX-A3G8`) and sample barcodes (`Tumor_SampleBarcode`, etc.).
- **PostgreSQL** `pancancer_clinical`: table **`clinical_info`** uses **`patient_id`** (TEXT) and long-form clinical attributes.

| Entity | DuckDB format | PostgreSQL `clinical_info` | Transformation |
| ------ | ------------- | ------------------------- | -------------- |
| Participant / patient | `ParticipantBarcode` like `TCGA-XX-NNNN` | `patient_id` often numeric suffix or TCGA-related id in clinical table | Use `JoinKeyResolver.resolve_tcga_id()` to normalize TCGA-style strings for comparison |

Resolution example: `JoinKeyResolver.resolve_tcga_id("TCGA-AB-1234")` → normalized token for matching (strip `TCGA-`, dashes, lowercase per implementation).

```python
# DuckDB RNASeq_Expression.ParticipantBarcode: "TCGA-06-0675"
# DuckDB Mutation_Data.ParticipantBarcode:     "TCGA-AX-A3G8"
# PostgreSQL clinical_info.patient_id:         align via resolver + sample id rules
resolved = resolver.resolve_tcga_id(duck_barcode)
```

**Deprecated:** older docs referred to a fictional `gene_expression.patient_id` / `mutations.patient_id` pair — the shipped schema uses **`RNASeq_Expression`** / **`Mutation_Data`** + **`clinical_info`** instead.

## Yelp Dataset — business_id / business_ref

Join **PostgreSQL** `review.business_id`, **DuckDB** `review.business_ref`, and **MongoDB** `business.business_id` / `checkin.business_id` using the same logical business id (may appear as `businessid_*` vs `businessref_*` in slices — normalize per `seed_yelp_postgres` / eval hints).

```text
PostgreSQL review.business_id:  "abc123def456xyz789ab12"  (TEXT)
DuckDB review.business_ref:     "businessref_1" / same id family  (VARCHAR)
MongoDB business.business_id:    "abc123def456xyz789ab12"  (STRING)
Transformation: map ref ↔ id when names differ; otherwise direct equality
```

## Injection Test

Q: How do I join PostgreSQL subscriber_id to MongoDB?
A: Use JoinKeyResolver().resolve_cross_db_join() from utils/join_key_resolver.py. For Telecom apply f"CUST-{subscriber_id}" to convert the PostgreSQL INT to the MongoDB STRING format.
