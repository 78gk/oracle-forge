# Unstructured Text Extraction Patterns for DAB

## Support Ticket Sentiment Extraction

**Field:** support_tickets.issue_description (TEXT) in MongoDB

**Extraction goal:** "negative sentiment" count

### Implementation

```python
negative_indicators = [
    'frustrated', 'angry', 'terrible', 'awful', 'worst',
    'broken', 'not working', 'failed', 'error', 'complaint',
    'unhappy', 'disappointed', 'useless', 'waste', 'terrible'
]

def extract_sentiment(text):
    text_lower = text.lower()
    is_negative = any(indicator in text_lower for indicator in negative_indicators)
    # Check for negation
    if 'not ' + indicator in text_lower:
        is_negative = False
    return 'negative' if is_negative else 'non-negative'
```

## Yelp Review Fact Extraction

Field: review.text (TEXT) in PostgreSQL

Extraction examples:

- "mentioned parking" → boolean
- "mentioned price" → boolean

### Implementation — Yelp Facility Mentions

```python
def extract_mentioned_facilities(text):
    facilities = ['parking', 'wifi', 'outdoor seating', 'delivery', 'price']
    text_lower = text.lower()
    return [facility for facility in facilities if facility in text_lower]
```

## Healthcare Note Extraction

Field: clinical_notes (TEXT) in MongoDB

Extraction: medication names, dosages, frequencies

### Implementation — Healthcare Medication Extraction

```python
medication_pattern = r'\b([A-Z][a-z]+)\s+(\d+\s*(mg|mcg|g|ml))\s+(daily|bid|tid|qid|weekly)\b'
matches = re.findall(medication_pattern, text)

# Returns: [('Lisinopril', '10 mg', 'daily'), ...]
```

## Yelp categories — Pipe-Separated Field (J5)

**Field:** `business.primary_categories` in **PostgreSQL** is a **pipe-separated string**, not an array or FK. Default **`yelp_user.db` (DuckDB) has no `business` table** — category filtering is done against Postgres `business`; **`useful`** votes are on **DuckDB `review.useful`**.

Example value: `"Restaurants|Pizza|Italian"`

**Do NOT use:** `WHERE primary_categories = 'Restaurants'` or `WHERE primary_categories LIKE '%Pizza%'`
(substring match causes false positives on partial category names).

**Correct SQL filter:**

```sql
WHERE '|' || primary_categories || '|' LIKE '%|' || :category || '|%'
```

**Correct Python filter:**

```python
# Exact element match after splitting
df['primary_categories'].str.split('|').apply(lambda cats: category in [c.strip() for c in cats])

# Or using CategoryMatcher utility
from utils.unstructured_extractor import CategoryMatcher
matches = df['primary_categories'].apply(lambda v: CategoryMatcher.match_pipe_field(v, category))
```

Join **`review.business_ref`** (DuckDB) to **`business.business_id`** (Postgres) / **`business.business_id`** (Mongo) per `join_key_mappings.md`.

## Critical Rule

Never return raw text when query asks for a count or structured fact.
Always apply extraction BEFORE counting or calculating.

## Injection Test

Q: How do I extract negative sentiment from support ticket text?
A: Use negative_indicators list with .lower() and any()

Q: How do I filter Yelp businesses by a single category?
A: Use pipe-split on `primary_categories`: `WHERE '|' || primary_categories || '|' LIKE '%|Pizza|%'.` Do NOT use plain `LIKE '%Pizza%'`.
