# Fiscal Calendar Definitions

## crmarenapro Dataset

**FY2025** = July 1 2024 – June 30 2025

SQL filter:
```sql
WHERE order_date BETWEEN '2024-07-01' AND '2025-06-30'
```

Do NOT use calendar year boundaries (Jan 1 – Dec 31) for any fiscal year query on crmarenapro.

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
