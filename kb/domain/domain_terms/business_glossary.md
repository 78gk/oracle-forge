# Domain Term Definitions by Dataset

## Telecom Industry

| Term | Naive Interpretation | Correct Definition (for DAB) |
| ---- | -------------------- | ----------------------------- |
| "active customer" | Has row in subscribers table | Purchased in last 90 days AND churn_date IS NULL |
| "churn" | Cancelled service | churn_date IS NOT NULL |
| "high-value customer" | High monthly_revenue | monthly_revenue > 100 AND plan_type = 'postpaid' |
| "fiscal quarter" | Calendar Q3 (Jul-Sep) | Telecom fiscal: Q3 = Oct-Dec |

## Retail (Yelp)

| Term | Naive Interpretation | Correct Definition |
| ---- | -------------------- | ------------------ |
| "popular business" | High review_count | review_count > 100 AND stars > 4.0 |
| "recent review" | Last 30 days | date > CURRENT_DATE - INTERVAL '30 days' |
| "power user" | High user.review_count | user.review_count > 50 AND user.fans > 10 |

## Healthcare

| Term | Naive Interpretation | Correct Definition |
| ---- | -------------------- | ------------------ |
| "readmission" | Same patient, same hospital | patient_id matches AND days_between < 30 |
| "out-of-network" | Provider not in network | provider_npi NOT IN network_list |
| "denied claim" | claim_status = 'denied' | status IN ('denied', 'rejected') |

## crmarenapro Dataset

| Term | Naive Interpretation | Correct Definition (for DAB) |
| ---- | -------------------- | ----------------------------- |
| "active customer" | Has row in customers table | Has made at least one purchase within the last 90 days: `WHERE last_purchase_date >= CURRENT_DATE - INTERVAL '90 days'`. Do NOT use row existence or `account_status = 'active'` alone. |
| "revenue" | SUM of all order amounts | `SUM(amount) WHERE status NOT IN ('refunded', 'cancelled', 'returned')`. Never sum the full orders table for revenue figures. |
| "NPS promoter" | Score > 8 on a 0–10 scale | crmarenapro uses a **–100 to +100 scale** (not 0–10). Promoter zone = score ≥ 50. Passive = –49 to 49. Detractor = score ≤ –50. Do NOT apply standard 0–10 NPS logic. |

## Where to Find Definitions

These definitions are NOT in database schemas.
Load this file before generating SQL for any query with ambiguous terms.

## Injection Test

Q: What does "active customer" mean in telecom?
A: Purchased in last 90 days AND churn_date IS NULL

Q: What does "active customer" mean in crmarenapro?
A: At least one purchase in the last 90 days. Filter: WHERE last_purchase_date >= CURRENT_DATE - INTERVAL '90 days'

Q: How is revenue calculated in crmarenapro?
A: SUM(amount) WHERE status NOT IN ('refunded', 'cancelled', 'returned')

Q: What is the NPS promoter threshold in crmarenapro?
A: Score >= 50 on the -100 to +100 scale (not the standard 0-10 scale)
