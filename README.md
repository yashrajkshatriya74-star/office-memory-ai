# 🧠 Office Memory AI

**Office Memory AI doesn't remember conversations. It remembers decisions — and why they were made.**

A Slack bot that captures organizational decisions, preserves the reasoning behind them, detects contradictions, tracks how decisions evolve over time, and helps teams understand not just *what* was decided — but *why*.

Built for the Slack AI Agent Hackathon (2026).

---

## The Problem

Every team makes important decisions in Slack — which tool to use, which architecture to pick, which policy to enforce. Months later, someone asks:

> "Why are we using PostgreSQL instead of DynamoDB?"

And the answer is usually: *"No idea, scroll through Slack and find out."*

Generic AI assistants (Slack AI, Copilot, Gemini) can **search** old messages. None of them understand that a *decision* is a distinct, first-class thing that deserves its own memory — with reasoning, alternatives considered, and a history of how it changed.

**Search finds messages. Office Memory AI remembers decisions.**

---

## What It Does

- **Detects decisions automatically** — watches channel messages and identifies when a real decision is being made (keyword filtering + LLM verification, to avoid false positives on casual chat).
- **Stores the reasoning, not just the outcome** — every decision is saved with *why* it was made, not just *what* was decided.
- **Answers with context, not just text** — ask `@OfficeMemoryAI why did we choose X?` and get a reasoned answer, with a link back to the original Slack message.
- **Tracks how decisions evolve** — if a decision is later changed, Office Memory AI recognizes the old one has been superseded and always answers with the current, authoritative decision — while still being aware of the history.
- **Flags contradictions proactively** — if someone makes a decision that conflicts with an earlier one, the bot immediately flags it in the thread, before it becomes a bigger problem.
- **Tracks rejected alternatives** — when a decision message mentions options that were considered and rejected, Office Memory AI remembers those too, so teams don't re-litigate the same debate months later.

---

## Example

**Message in Slack:**
> "We've decided to go with PostgreSQL instead of DynamoDB because of better query flexibility."

**Later, someone asks:**
> `@OfficeMemoryAI why did we choose PostgreSQL?`

**Office Memory AI replies:**
> We're using **PostgreSQL**.
> ✅ **Decision**: Chosen instead of DynamoDB
> ✅ **Why**: Better query flexibility
> ❌ Rejected alternative: DynamoDB — limited query capabilities

**If a conflicting decision is made later:**
> "We've decided to use MySQL for the new service instead of PostgreSQL."

**Office Memory AI immediately flags:**
> ⚠️ This appears to conflict with an earlier decision: *[PostgreSQL decision summary]*

---

## Tech Stack

| Component | Technology |
|---|---|
| Slack integration | Slack Bolt SDK (Socket Mode — no public URL needed) |
| Language model | Qwen (Alibaba Cloud DashScope), OpenAI-compatible client |
| Decision storage & retrieval | Lightweight JSON + numpy vector store |
| Embeddings | `all-MiniLM-L6-v2` (local, free, offline) |
| Backend | Python |

**Why a custom vector store instead of a heavier database?** It keeps the project dependency-light and easy to run anywhere with zero infrastructure setup — a deliberate tradeoff for a fast-moving hackathon build, not a technical limitation of the approach.

---

## Architecture

```
Slack message
     │
     ▼
is_decision_message()  ──► keyword filter + LLM classifier
     │ (if true)
     ▼
extract_decision_summary()  ──► decision, reasoning, rejected alternatives
     │
     ▼
get_similar_past_decisions() + check_contradiction()  ──► proactive conflict detection
     │
     ▼
store_decision()  ──► saved to memory with timestamp, author, source link
     │
     ▼
[Later] @OfficeMemoryAI <question>
     │
     ▼
query_decisions()  ──► retrieve most relevant past decisions
     │
     ▼
answer_query()  ──► LLM generates a reasoned, source-linked answer
```

---

## Setup

```bash
git clone <this-repo>
cd office-memory-ai
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps), enable Socket Mode, and add the following Bot Token Scopes: `channels:history`, `channels:read`, `chat:write`, `app_mentions:read`, `users:read`.
2. Subscribe to bot events: `message.channels`, `app_mention`.
3. Copy `.env.example` to `.env` and fill in `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`, and `QWEN_API_KEY`.
4. Run the bot:
   ```bash
   cd app
   python main.py
   ```
5. Invite the bot to a channel (`/invite @OfficeMemoryAI`) and start making decisions.

---

## What's Next (Roadmap)

- **Decision impact analysis** — "If we reverse this decision, what else breaks?"
- **Decision expiry nudges** — proactively flag decisions that are old enough that the underlying context may have changed.
- **Cross-channel memory** — currently scoped per-channel; extending to a workspace-wide decision graph.
- **Slack-native UI (Block Kit)** — richer, interactive decision cards instead of plain text replies.

---

## Why This Matters Beyond the Hackathon

Every growing company loses institutional knowledge as people leave, teams reorganize, and Slack history piles up. Office Memory AI turns scattered decisions into a searchable, reasoned, always-current source of truth — the kind of tool that gets more valuable the longer a team uses it.

---

*Built solo for the Slack AI Agent Hackathon, July 2026.*

