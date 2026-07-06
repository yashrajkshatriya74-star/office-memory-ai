"""
Office Memory AI - Slack Bot
Socket Mode use kar rahe hain, isliye koi public URL/hosting nahi chahiye local dev ke liye.

Run: python app/main.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from llm import is_decision_message, extract_decision_summary, answer_query, check_contradiction
from memory_store import store_message, store_decision, query_decisions, get_similar_past_decisions

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
)

BOT_USER_ID = None  # runtime pe fill hoga, taaki bot apne hi messages pe react na kare


@app.event("app_mention")
def handle_mention(event, say, client):
    """
    Jab koi bot ko @mention karke sawal poochta hai.
    Example: "@OfficeMemoryAI why did we choose DynamoDB over Redis?"
    """
    text = event["text"]
    channel = event["channel"]

    # Bot ka apna mention tag hata do question se
    question = text.split(">", 1)[-1].strip() if ">" in text else text

    say(text="One sec, checking past decisions... 🔍", thread_ts=event.get("ts"))

    results = query_decisions(question, n_results=3)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        say(
            text="I couldn't find any past decision on this topic in this channel. "
                 "It might have been discussed elsewhere, or hasn't been recorded yet.",
            thread_ts=event.get("ts"),
        )
        return

    context_block = "\n\n".join(
        f"[Message link: https://slack.com/archives/{channel}/p{m['ts'].replace('.', '')}]\n{doc}"
        for doc, m in zip(docs, metas)
    )

    answer = answer_query(question, context_block)
    say(text=answer, thread_ts=event.get("ts"))


@app.event("message")
def handle_message(event, say, client):
    """
    Har normal message pe chalta hai. Bot messages, edits, deletes ignore karte hain.
    Decision-like message mile to store + tag karte hain.
    """
    # Skip bot's own messages, message edits/deletes, and messages with subtypes
    if event.get("subtype") is not None or event.get("bot_id"):
        return

    text = event.get("text", "")
    channel = event["channel"]
    user = event.get("user", "unknown")
    ts = event["ts"]

    if not text.strip():
        return

    # Har message ko general store mein daal do (future context ke liye)
    store_message(channel, user, text, ts)

    # Ab check karo ki ye ek decision hai kya
    if is_decision_message(text):
        summary = extract_decision_summary(text)

        # Naya decision store karne se PEHLE, dekho kya isi topic pe pehle koi decision hai
        similar_past = get_similar_past_decisions(text, channel)
        contradiction_note = check_contradiction(text, similar_past) if similar_past else ""

        store_decision(channel, user, text, summary["raw"], ts)

        # React karke visually confirm karo ki bot ne isse "decision" mark kiya
        try:
            client.reactions_add(channel=channel, timestamp=ts, name="brain")
        except Exception:
            pass  # agar already reacted ya permission issue, ignore silently

        confirmation = (
            f"📌 Decision logged and saved to memory. Ask `@OfficeMemoryAI` "
            f"anytime to recall this decision and the reasoning behind it."
        )

        if contradiction_note:
            confirmation += f"\n\n⚠️ {contradiction_note}"
            try:
                client.reactions_add(channel=channel, timestamp=ts, name="warning")
            except Exception:
                pass

        say(text=confirmation, thread_ts=ts)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("🧠 Office Memory AI is running... Slack mein jaake test karo!")
    handler.start()
