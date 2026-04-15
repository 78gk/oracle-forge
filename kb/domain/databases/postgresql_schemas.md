# PostgreSQL Schemas for DAB Datasets

## Yelp Dataset (primary for validation)

### Table: business**

- business_id (TEXT, PK) - format: "abc123def456"
- name (TEXT)
- city (TEXT)
- state (TEXT) - 2-letter codes: CA, NY, TX
- stars (FLOAT) - 1.0 to 5.0, 0.5 increments
- review_count (INT)
- is_open (INT) - 0 = closed, 1 = open

### Table: review**

- review_id (TEXT, PK) - format: "xyz789abc123"
- user_id (TEXT) - foreign key to user.user_id
- business_id (TEXT) - foreign key to business.business_id (map `businessid_N` ↔ `businessref_N` when joining to DuckDB)
- stars (INT) - 1 to 5 (same semantic as DuckDB `rating`; PostgreSQL uses the name `stars`)
- date (TEXT) - format: 'YYYY-MM-DD'
- text (TEXT) - unstructured review content (requires extraction)

### Table: user**

- user_id (TEXT, PK) - format: "user_12345"
- review_count (INT)
- yelping_since (TEXT) - 'YYYY-MM-DD'
- average_stars (FLOAT)

## Telecom Dataset

### Table: subscribers**

- subscriber_id (INT, PK) - numeric only, 7-10 digits
- plan_type (TEXT) - 'prepaid', 'postpaid', 'business'
- activation_date (DATE)
- churn_date (DATE) - NULL if active
- monthly_revenue (DECIMAL)

### Table: support_tickets**

- ticket_id (TEXT, PK) - format: "TKT-{8-digit}"
- subscriber_id (INT) - foreign key (INT, matches subscribers.subscriber_id)
- issue_type (TEXT)
- resolution_time_hours (INT)

## Healthcare Dataset

### Table: patients**

- patient_id (INT, PK) - numeric only, 9 digits (e.g. 987654321)
- date_of_birth (DATE)
- insurance_plan_id (TEXT)
- state (TEXT) - 2-letter code

### Table: claims**

- claim_id (TEXT, PK) - format: "CLM-{5-digit}"
- patient_id (INT) - foreign key to patients.patient_id
- provider_npi (INT) - 10-digit NPI number (e.g. 1234567890)
- service_date (DATE)
- amount (DECIMAL)
- status (TEXT) - values: 'paid', 'denied', 'rejected', 'pending'

**Critical Healthcare Join Note:** patient_id is INT in PostgreSQL, "PT-{INT}" in MongoDB. provider_npi is INT in PostgreSQL, "NPI-{INT}" in MongoDB. Use resolve_join_key for both.

## Critical Join Note

Customer IDs in PostgreSQL are INT. Same customers in MongoDB are "CUST-{INT}" strings.
**Use resolve_join_key with transformation: f"CUST-{customer_id}"**

## Injection Test

Q: What is the format of Yelp business_id?
A: "abc123def456" (TEXT)
