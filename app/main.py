"""
Office Memory AI - Slack Bot
Socket Mode use kar rahe hain, isliye koi public URL/hosting nahi chahiye local dev ke liye.

Run: python app/main.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from slack_bolt import App, Assistant
from slack_bolt.adapter.socket_mode import SocketModeHandler

from llm import is_decision_message, extract_decision_summary, answer_query, check_contradiction
from memory_store import store_message, store_decision, query_decisions, get_similar_past_decisions

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
)

assistant = Assistant()  # Slack's native "Agents & AI Apps" side-panel feature

BOT_USER_ID = None  # runtime pe fill hoga, taaki bot apne hi messages pe react na kare


def answer_decision_question(question: str, channel: str) -> str:
    """
    Shared logic: purane decisions retrieve karke reasoned answer generate karta hai.
    Ye function @mention aur AI Assistant side-panel dono se use hota hai.
    """
    results = query_decisions(question, n_results=3)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return (
            "I couldn't find any past decision on this topic in this channel. "
            "It might have been discussed elsewhere, or hasn't been recorded yet."
        )

    context_block = "\n\n".join(
        f"[Message link: https://slack.com/archives/{channel}/p{m['ts'].replace('.', '')}]\n{doc}"
        for doc, m in zip(docs, metas)
    )
    return answer_query(question, context_block)


# ---------------------------------------------------------------------------
# Slack AI Assistant side-panel (Slack's native "Agents & AI Apps" feature)
# ---------------------------------------------------------------------------

@assistant.thread_started
def start_assistant_thread(say, set_suggested_prompts, logger):
    """Jab user pehli baar AI Assistant panel kholta hai."""
    print("🟢 DEBUG: assistant_thread_started event received!")
    try:
        say("Hi! I'm Office Memory AI. Ask me why a past team decision was made, "
            "or what alternatives were considered.")
        set_suggested_prompts(
            prompts=[
                {"title": "Why did we choose our current database?",
                 "message": "Why did we choose our current database?"},
                {"title": "What decisions were made recently?",
                 "message": "What decisions were made recently?"},
            ]
        )
    except Exception as e:
        logger.exception(f"Failed to start assistant thread: {e}")


@assistant.user_message
def respond_in_assistant_thread(payload, say, set_status, logger):
    """Jab user AI Assistant panel mein koi sawal type karta hai."""
    print(f"🟢 DEBUG: assistant user_message event received! Text: {payload.get('text')}")
    try:
        question = payload.get("text", "")
        channel = payload.get("channel", "")
        set_status("Checking past decisions...")
        answer = answer_decision_question(question, channel)
        say(answer)
    except Exception as e:
        logger.exception(f"Failed to respond in assistant thread: {e}")
        say("Sorry, something went wrong while looking that up.")


app.use(assistant)


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

    answer = answer_decision_question(question, channel)
    say(text=answer, thread_ts=event.get("ts"))


@app.event("message")
def handle_message(event, say, client):
    """
    Har normal CHANNEL message pe chalta hai. Bot messages, edits, deletes ignore karte hain.
    Decision-like message mile to store + tag karte hain.

    IMPORTANT: DM messages (channel ID 'D' se start hoti hai) yahan se skip kiye jate hain,
    kyunki wo Assistant class (side-panel) exclusively handle karti hai. Agar ye skip nahi
    karte, to generic handler DM messages ko bhi intercept kar leta tha aur Assistant
    class ka code kabhi trigger hi nahi hota tha.
    """
    channel = event["channel"]

    if channel.startswith("D"):
        # DM hai. Normally Assistant class (assistant.user_message) ise handle karti hai,
        # lekin agar assistant_thread_started event kisi wajah se miss ho gaya ho
        # (jaise app restart/crash ke beech mein), to Bolt is thread ko "assistant thread"
        # ke roop mein recognize nahi karta aur events yahan generic handler tak aa jate hain.
        # Isliye fallback: yahan bhi seedha answer de dete hain, taaki DM mein poocha gaya
        # sawal kabhi bhi unanswered na rahe.
        if event.get("subtype") is not None or event.get("bot_id"):
            return
        text = event.get("text", "")
        if not text.strip():
            return
        print(f"🟡 DEBUG: DM fallback handling message: {text}")
        answer = answer_decision_question(text, channel)
        say(text=answer)
        return

    # Skip bot's own messages, message edits/deletes, and messages with subtypes
    if event.get("subtype") is not None or event.get("bot_id"):
        return

    text = event.get("text", "")
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
