# Signal Corps Engagement Log - Oracle Forge

_All external posts, threads, and community interactions. Updated daily._
_Covers: X, Reddit, Medium, LinkedIn, Discord_

---

## Week 8 (Apr 7-11, 2026)

### Project Milestones (context for content grounding)

| Date | Milestone | Owner | Commit/Evidence |
|------|-----------|-------|-----------------|
| 2026-04-07 | KB v0.1 initial structure created | Mikiyas | -- |
| 2026-04-08 | KB v1.0 Architecture layer: 6 docs (memory system, autoDream, tool scoping, OpenAI 6-layer, conductor/worker, eval harness). 6/6 injection tests pass | Mikiyas | `8f6caf9` |
| 2026-04-09 | KB v2.0 Domain layer: 9 docs (4 DB schemas, join key mappings, cross-DB patterns, text extraction, sentiment, business glossary). 9/9 injection tests pass | Mikiyas | `76aa867` - `9cf152f` |
| 2026-04-09 | Repo initialized on GitHub, .gitignore configured | Eyor, Mikiyas | `46d261e`, `6ab02eb` |
| 2026-04-10 | KB v3.0 Corrections layer: 4 docs (failure log, failure by category, resolved patterns, regression prevention). 6/6 injection tests pass. Total: 21/21 | Mikiyas | `4d976ef` |
| 2026-04-10 | Inception document committed to planning/ | Gashaw, Mikiyas | `91634c1` |
| 2026-04-10 | REFERENCEDOC.md added for team onboarding | Mikiyas | `a6fbd59` |
| 2026-04-11 | Signal Corps engagement infrastructure created (this file, community log, resource report) | Kirubel | feat/signal-corps-engagement |

### X/Twitter

| Date | Author | Type | Content Summary | Link | Likes | Replies |
|------|--------|------|-----------------|------|-------|---------|
| 2026-04-09 | Kirubel | Tweet | PostgreSQL + MongoDB friction: ill-formatted join keys in a single query. Links to DAB paper + repo | [link](https://x.com/kirubeltewodro2/status/2042250450888503584) | 1 | 0 |
| 2026-04-09 | Kirubel | Tweet | DAB 38% pass@1 ceiling = engineering gap signal, not benchmark flaw | [link](https://x.com/kirubeltewodro2/status/2042263948691415485) | 1 | 1 |
| 2026-04-10 | Kirubel | Tweet | Medium article announcement: cross-DB join key format mismatch | [link](https://x.com/kirubeltewodro2/status/2042676161499570186) | 1 | 0 |

### Medium/LinkedIn

| Date | Author | Title | Platform | Word Count | Link | Views |
|------|--------|-------|----------|------------|------|-------|
| 2026-04-10 | Kirubel | Engineering Resilience: Solving the Cross-Database Join Key Format Mismatch in AI Agents | Medium | ~1200 | [link](https://medium.com/@kirutew17654321/engineering-resilience-solving-the-cross-database-join-key-format-mismatch-in-ai-agents-ffb17b9d5a02) | -- |
| 2026-04-11 | Meseret | The Silent Killer of AI Data Agents (And How We're Engineering Around It) | LinkedIn | ~1800 | [link](https://www.linkedin.com/pulse/silent-killer-ai-data-agents-how-were-engineering-around-bolled-rsg8f ) | 52 |
### Reddit

| Date | Author | Subreddit | Title | Link | Upvotes | Comments |
|------|--------|-----------|-------|------|---------|----------|
| 2026-04-11 | Kirubel | r/learnmachinelearning | DataAgentBench shows the best frontier model hits 38% on realistic multi-DB data queries - what's actually causing the failures? | [link](https://www.reddit.com/r/learnmachinelearning/comments/1sieo3g/dataagentbench_shows_the_best_frontier_model_hits/) | -- | -- |
| 2026-04-11 | Kirubel | r/LocalLLaMA | I kept running into cases where retrieval was the bottleneck -- injection testing with Groq Llama (21/21 pass rate) | [link](https://www.reddit.com/r/LocalLLaMA/comments/1siqbda/i_kept_running_into_cases_where_retrieval_was/) | -- | 1 |

### Reddit Replies (substantive comments in threads)

| Date | Author | Subreddit | Replying To | Summary | Link |
|------|--------|-----------|-------------|---------|------|
| 2026-04-11 | Kirubel | r/LocalLLaMA | u/matt-k-wong asking about model size | Clarified: Llama 3.3 70B via Groq. Explained structured docs (tables + code) outperform prose even at 70B -- same info as prose failed injection test, as table passed immediately. Invited comparison across param counts. | [thread](https://www.reddit.com/r/LocalLLaMA/comments/1siqbda/i_kept_running_into_cases_where_retrieval_was/) |

### LinkedIn Replies (comments received on articles)

| Date | Author | Article | From | Comment Summary | Link |
|------|--------|---------|------|-----------------|------|
| 2026-04-12 | Meseret | The Silent Killer of AI Data Agents | The AI Agent Index (19 followers) | "Silent failures are genuinely harder to handle than loud ones. Confident wrong answers erode trust without leaving a clear signal to debug. The No data found problem usually traces back to schema mismatches or query construction issues that only surface at the edges of real-world data." | [link](https://www.linkedin.com/pulse/silent-killer-ai-data-agents-how-were-engineering-around-bolled-rsg8f ) |

### Discord

| Date | Author | Server/Channel | Topic | Link |
|------|--------|----------------|-------|------|
| -- | -- | -- | -- | -- |

---
### Engagement Metrics

| Date | Platform | Content | Reactions | Comments | Impressions | Views |
|------|----------|---------|-----------|----------|-------------|-------|
| 2026-04-11 | LinkedIn | The Silent Killer of AI Data Agents (Meseret) | 28 | 1,132 | 52 |

### Internal Slack Daily Posts

| Date | Author | Channel | Content Summary |
|------|--------|---------|-----------------|
| 2026-04-07 to 2026-04-11 | Meseret | #oracle-standup | Daily Signal Corps updates posted every working day covering: what shipped, what is stuck, what is next, community intel gathered. 5 posts total across Week 8. |
### Internal Slack Daily Posts

| Author | Channel | Period | Content Summary |
|--------|---------|--------|-----------------|
| Kirubel | #oracle-standup | 2026-04-07 to 2026-04-11 | Posted daily Slack updates across all 5 days of Week 8 based on standup discussions and GitHub commit status. Updates covered: KB layer completions, injection test results, X thread publications, Medium article launch, Reddit posts, and Signal Corps infrastructure setup. 5 posts total. |

---

### Google Meet Standup Facilitation

| Author | Period | Role | Summary |
|--------|--------|------|---------|
| Meseret | 2026-04-07 to 2026-04-11 | Standup Facilitator | Led  daily Google Meet standups across Week 8. Responsibilities included: opening each session, reminding team members to join, giving each of the 6 members floor time to share progress, asking targeted questions about blockers and next steps, and ensuring alignment between Drivers, Intelligence Officers, and Signal Corps before closing each session. |

## Week 9 (Apr 14-18, 2026)

### X/Twitter

| Date | Author | Type | Content Summary | Link | Likes | Replies |
|------|--------|------|-----------------|------|-------|---------|
| | | | | | | |

### Medium/LinkedIn

| Date | Author | Title | Platform | Word Count | Link | Views |
|------|--------|-------|----------|------------|------|-------|
| | Meseret | TBD | LinkedIn/Medium | -- | -- | -- |

### Reddit

| Date | Author | Subreddit | Title | Link | Upvotes | Comments |
|------|--------|-----------|-------|------|---------|----------|
| | | | | | | |

---

## Community Intelligence

_External responses or findings that changed the team's technical approach._

| Date | Source | Finding | Impact on Build |
|------|--------|---------|-----------------|
| 2026-04-11 | r/MachineLearning | Posting blocked: account too new or karma too low for r/MachineLearning. Pivoted to r/learnmachinelearning | Adjusted community targeting. r/learnmachinelearning has lower barrier, still relevant audience. Will build karma for r/MachineLearning access in Week 9. |

---

## Engagement Summary Stats

### Week 8 Totals
- **X posts:** 3
- **Medium articles:** 1 (published, 600+ words)
- **Reddit posts:** 2
- **Reddit comments/replies:** 0 (target: begin deploying reply templates)
- **Discord engagement:** 0
- **LinkedIn articles:** 0 (Meseret's pending)

### Accounts Tracked for Reply-Threading

| Account | Platform | Focus Area | Link |
|---------|----------|------------|------|
| @shipp_ai | X | AI engineering | https://x.com/shipp_ai |
| @_avichawla | X | Data/ML engineering | https://x.com/_avichawla |
| @himanshustwts | X | AI/ML threads | https://x.com/himanshustwts |
| @sh_reya | X | AI engineering | https://x.com/sh_reya |
