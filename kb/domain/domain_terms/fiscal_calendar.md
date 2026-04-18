# Fiscal Calendar Definitions

## crmarenapro Dataset

**FY2025** = July 1 2024 – June 30 2025.

Use fiscal date filters **only when** the active table has an appropriate date column (e.g. `order_date`, `createddate` on **`"Case"`**). PostgreSQL **`crm_support`** does **not** define `finance.fact_revenue`; pick a real date column after introspection.

Example filter shape (replace `your_date_col` and table):

```sql
WHERE your_date_col BETWEEN '2024-07-01' AND '2025-06-30'
```

Do NOT use calendar year boundaries (Jan 1 – Dec 31) for fiscal-year questions when the domain uses July–June fiscal years.

| Fiscal Year | Start | End |
|-------------|-------|-----|
| FY2023 | 2022-07-01 | 2023-06-30 |
| FY2024 | 2023-07-01 | 2024-06-30 |
| FY2025 | 2024-07-01 | 2025-06-30 |

## Telecom Dataset

Telecom fiscal quarters differ from calendar quarters:

| Telecom Fiscal Q | Calendar Months |
|-----------------|-----------------|
| Q1 | Jan–Mar |
| Q2 | Apr–Jun |
| Q3 | Oct–Dec |
| Q4 | Jul–Sep |

## Injection Test

Q: What date range is FY2025 for crmarenapro?
A: July 1 2024 – June 30 2025. SQL: WHERE order_date BETWEEN '2024-07-01' AND '2025-06-30'
