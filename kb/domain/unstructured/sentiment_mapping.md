# Sentiment Mapping for DAB Unstructured Fields

## Complete Sentiment Lexicon

### Negative Indicators (always check .lower())

frustrated, angry, terrible, awful, worst, broken, not working,
failed, error, complaint, unhappy, disappointed, useless, waste,
horrible, unacceptable, furious, annoyed, upset, ridiculous,
pathetic, disgusting, outrageous, fed up, sick of, done with,
never again, worst ever, zero stars, waste of time, waste of money

### Informal / Slang Negative Indicators

wtf, smh, ugh, omg this is bad, seriously, beyond bad, complete joke,
absolute disaster, total failure, beyond frustrated

### Sarcasm Markers (classify as negative)

"great, thanks for nothing", "oh wonderful", "just what I needed" (when followed by negative context),
"amazing how", "sure that helps", "fantastic job" (ironic — check surrounding context for failure words)

### Positive Indicators (for completeness)

excellent, great, amazing, wonderful, happy, satisfied, perfect,
outstanding, fantastic, helpful, quick, easy, recommended

## Negation Handling

If "not" precedes indicator, flip sentiment:

- "not good" → negative
- "not bad" → non-negative (not positive)
- "not happy" → negative
- "not satisfied" → negative
- "not working" → negative (already in negative list)
- "couldn't be better" → positive (double negative = positive)

## Mixed Sentiment Rule

If text contains both positive and negative indicators, **negative wins**:

```python
has_negative = any(ind in text_lower for ind in negative_indicators)
has_positive = any(ind in text_lower for ind in positive_indicators)
if has_negative:
    return 'negative'  # negative overrides positive in support ticket context
return 'positive' if has_positive else 'non-negative'
```

## Implementation

```python
def get_sentiment(text):
    text_lower = text.lower()

    # Check for negation
    if ' not ' in text_lower:
        for indicator in negative_indicators:
            if f'not {indicator}' in text_lower:
                return 'non-negative'

    # Standard check
    if any(indicator in text_lower for indicator in negative_indicators):
        return 'negative'
    return 'non-negative'
```

## Counting Negative Mentions

For query "count negative sentiment mentions":

1. Extract sentiment for each text field
2. Filter where sentiment == 'negative'
3. Count results

DO NOT: Return raw text and let user count.
DO: Return integer count.

## Bulk Classification — Labelled Examples (U3)

For `SentimentClassifier.classify_bulk()` applied to a batch of Yelp reviews:

| Review Sample | Expected Label | Notes |
| ------------- | -------------- | ----- |
| "Great food, amazing service, will definitely return!" | positive | Clear positive keywords |
| "Terrible wait, rude staff, never coming back" | negative | Clear negative keywords |
| "The food was okay I guess, nothing special" | neutral | No keyword matches |
| "Best pizza in town but slow delivery" | positive | pos dominates; 1 neg word does not flip if ratio >= 0.6 |
| "Worst experience ever — cold food, horrible staff, disgusting" | negative | Multiple strong negatives |

### Sarcasm Flags

Sarcasm patterns classify as **negative** when they combine a positive phrase with failure context:

- "Oh great, the food arrived cold again" → negative
- "Amazing how they can get every order wrong" → negative
- "Fantastic service — waited 2 hours" → negative

### Mixed-Review Edge Cases

When `pos / (pos + neg) < 0.6`, classify as negative. Example:

- 3 reviews matched positive keywords, 3 matched negative → ratio = 0.5 → **negative**
- 6 positive, 4 negative → ratio = 0.6 → **positive** (threshold is inclusive)

### Short Reviews

Reviews under ~5 words often match no keywords → classified as **neutral**. Do not force-classify.

## Injection Test

Q: How does negation affect sentiment classification?
A: "not good" is negative, "not bad" is non-negative.

Q: What label does classify_bulk return for a batch with no keyword matches?
A: neutral
