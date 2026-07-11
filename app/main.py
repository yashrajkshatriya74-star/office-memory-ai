"""
Office Memory AI - Slack Bot
Socket Mode use kar rahe hain, isliye koi public URL/hosting nahi chahiye local dev ke liye.

Run: python app/main.py
"""
import os
import time
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


def process_incoming_text(text: str, channel: str, user: str, ts: str, say, client,
                           thread_ts=None, answer_if_not_decision: bool = True):
    """
    Shared logic: har incoming text (channel message ya DM) do mein se ek hai —
    (1) ek naya decision jo log karna hai, ya (2) ek sawal jiska jawab dena hai.
    Pehle decision-check karte hain; decision na ho to hi question maan ke jawab dete hain.
    Ye function normal channel messages aur DM fallback dono se use hota hai, taaki
    dono jagah decisions sahi se detect + store ho sakein.

    answer_if_not_decision=False rakho normal channel messages ke liye — warna bot har
    non-decision channel message ko bhi "question" samajh ke reply karega (spam). DM/Assistant
    panel mein ye True rehna chahiye, kyunki wahan har message ya to decision hai ya sawal.
    """
    # Har message ko general store mein daal do (future context ke liye)
    store_message(channel, user, text, ts)

    if is_decision_message(text):
        summary = extract_decision_summary(text)

        # Naya decision store karne se PEHLE, dekho kya isi topic pe pehle koi decision hai
        similar_past = get_similar_past_decisions(text, channel)
        contradiction_note = check_contradiction(text, similar_past) if similar_past else ""

        store_decision(channel, user, text, summary["raw"], ts)

        # React karke visually confirm karo ki bot ne isse "decision" mark kiya
        # (DMs mein reactions_add fail ho sakta hai agar channel type support na kare, isliye guarded hai)
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

        say(text=confirmation, thread_ts=thread_ts)
    elif answer_if_not_decision:
        # Decision nahi hai, to question samajh ke answer do
        answer = answer_decision_question(text, channel)
        say(text=answer, thread_ts=thread_ts)
    # else: normal channel chit-chat hai, decision bhi nahi — chup rehna hai (spam avoid)


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
    """
    Jab user AI Assistant panel mein kuch type karta hai — ye ek naya decision
    ho sakta hai (jise store karna hai) ya ek sawal (jiska jawab dena hai).
    process_incoming_text dono cases khud detect kar leta hai.
    """
    text = payload.get("text", "")
    channel = payload.get("channel", "")
    user = payload.get("user", "unknown")
    ts = payload.get("ts") or payload.get("event_ts") or str(time.time())
    print(f"🟢 DEBUG: assistant user_message event received! Text: {text}")
    try:
        if not text.strip():
            return
        set_status("Checking past decisions...")
        process_incoming_text(text, channel, user, ts, say, app.client)
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
    Har incoming message pe chalta hai — channel ya DM dono. Bot messages, edits,
    deletes ignore karte hain.

    - Normal channel message: sirf decision-detect + store karta hai, chit-chat pe
      chup rehta hai (sawaalon ka jawab sirf @mention se milta hai).
    - DM (channel ID 'D' se start): Assistant class (side-panel) normally isse handle
      karti hai, lekin agar assistant_thread_started event miss ho jaye (app restart
      ke beech), to Bolt event yahan fallback mein aa jaata hai. Isliye yahan bhi
      decision-detect pehle karte hain, phir hi question maan ke jawab dete hain.
    """
    channel = event["channel"]

    # Skip bot's own messages, message edits/deletes, and messages with subtypes
    if event.get("subtype") is not None or event.get("bot_id"):
        return

    text = event.get("text", "")
    user = event.get("user", "unknown")
    ts = event["ts"]

    if not text.strip():
        return

    if channel.startswith("D"):
        # DM hai. Normally Assistant class (assistant.user_message) ise handle karti hai,
        # lekin agar assistant_thread_started event kisi wajah se miss ho gaya ho
        # (jaise app restart/crash ke beech mein), to Bolt is thread ko "assistant thread"
        # ke roop mein recognize nahi karta aur events yahan generic handler tak aa jate hain.
        # Isliye fallback: yahan bhi PEHLE decision-check karte hain, phir hi question maan
        # ke jawab dete hain — pehle ye seedha answer_decision_question call karta tha, jiski
        # wajah se DM mein bheja gaya decision kabhi store hi nahi hota tha.
        print(f"🟡 DEBUG: DM fallback handling message: {text}")
        process_incoming_text(text, channel, user, ts, say, client)
        return

    # Normal channel message: sirf decision-check + store karo. Random chit-chat pe reply nahi
    # karna — sawaalon ka jawab sirf @mention se milta hai (handle_mention upar).
    process_incoming_text(text, channel, user, ts, say, client, thread_ts=ts,
                           answer_if_not_decision=False)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("🧠 Office Memory AI is running... Slack mein jaake test karo!")
    handler.start()
