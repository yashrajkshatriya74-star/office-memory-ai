"""
LLM wrapper - Qwen (DashScope OpenAI-compatible endpoint) use kar rahe hain.
Agar OpenAI use karna hai to bas .env mein OPENAI_API_KEY daal dena aur
niche client init me base_url hata dena.
"""
import os
from openai import OpenAI

QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

EMBEDDING_MODEL = "text-embedding-v3"


def get_embedding(text: str) -> list:
    """
    Qwen/DashScope ke embedding API se vector nikalta hai.
    Local sentence-transformers/torch ki jagah ye use kar rahe hain — halka hai,
    koi heavy dependency nahi, aur Python version compatibility issues avoid karta hai.
    """
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def ask_llm(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Simple single-turn completion call."""
    response = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def is_decision_message(text: str) -> bool:
    """
    Fast + cheap classifier: kya ye message ek 'decision' hai?
    Pehle keyword filter (free, instant), phir LLM se confirm (sirf borderline cases pe).
    """
    text_lower = text.lower()
    keywords = [
        "we'll go with", "we will go with", "decided", "decision", "final call",
        "let's use", "let's go with", "finalize", "finalized", "agreed", "we're going with",
        "chose", "choosing", "moving forward with", "changing", "changed", "switching",
        "switched", "update:", "revised", "revising", "instead of", "going with",
    ]
    if not any(kw in text_lower for kw in keywords):
        return False

    # Keyword mila, ab LLM se double-check (avoid false positives like "I decided to eat lunch")
    verdict = ask_llm(
        system_prompt=(
            "You classify Slack messages. Reply with exactly one word: YES or NO. "
            "YES only if the message describes a real work/project/technical decision "
            "made by the team (e.g. choosing a tool, approach, architecture, vendor, policy). "
            "NO for casual chat, personal plans, or vague statements."
        ),
        user_prompt=f"Message: \"{text}\"",
        max_tokens=5,
    )
    return "YES" in verdict.upper()


def extract_decision_summary(text: str, thread_context: str = "") -> dict:
    """
    Decision message se structured summary nikalta hai: kya decide hua, kyun (reasoning),
    aur agar mention hui hon to kaunsi alternatives reject ki gayi.
    """
    context_block = f"\nThread context (other messages around it):\n{thread_context}" if thread_context else ""
    result = ask_llm(
        system_prompt=(
            "Extract the core decision and its reasoning from this Slack message/thread. "
            "Respond in this exact format:\n"
            "DECISION: <one line, what was decided>\n"
            "REASONING: <bullet points of why, if mentioned, else 'Not specified'>\n"
            "REJECTED_ALTERNATIVES: <comma-separated list of alternatives that were explicitly "
            "mentioned as rejected/not chosen, e.g. 'Redis, DynamoDB'. If none are mentioned, write 'None mentioned'>\n"
            "Respond entirely in English, with no words or characters from other languages."
        ),
        user_prompt=f"Message: \"{text}\"{context_block}",
        max_tokens=300,
    )
    return {"raw": result}


def check_contradiction(new_decision_text: str, past_decisions: list) -> str:
    """
    Naya decision aur purane related decisions ko compare karke batata hai
    kya ye ek genuine update/contradiction hai. Agar haan, ek chhota warning
    banata hai jo Slack reply mein include hoga. Agar koi real conflict/update
    nahi hai, empty string return karta hai.
    """
    if not past_decisions:
        return ""

    past_block = "\n\n".join(
        f"[{i+1}] {d['text']}" for i, d in enumerate(past_decisions)
    )

    result = ask_llm(
        system_prompt=(
            "You compare a NEW decision message against one or more PAST related decisions "
            "from the same team. Determine if the new message changes, reverses, or conflicts "
            "with any past decision. "
            "If yes, respond with ONE short sentence starting with 'This appears to update/conflict with an earlier decision: ' "
            "followed by a brief description of the earlier decision. "
            "If the new message is simply consistent with or unrelated to the past decisions, "
            "respond with exactly: NONE. "
            "Respond entirely in English."
        ),
        user_prompt=f"NEW decision: \"{new_decision_text}\"\n\nPAST related decisions:\n{past_block}",
        max_tokens=100,
    )
    result = result.strip()
    if result.upper() == "NONE" or not result:
        return ""
    return result


def answer_query(question: str, retrieved_context: str) -> str:
    """RAG-style answer generation using retrieved decision records."""
    return ask_llm(
        system_prompt=(
            "You are Office Memory AI, a Slack bot that helps teams recall past decisions. "
            "Answer the question using ONLY the provided context. "
            "If the context has a clear decision, explain what was decided and why, in a friendly, "
            "concise Slack-message style (use short lines/bullets). "
            "If nothing relevant is found, say so honestly instead of guessing. "
            "IMPORTANT: Respond entirely in English. Do not include any words or characters "
            "from other languages, even single words."
        ),
        user_prompt=f"Question: {question}\n\nRelevant past messages:\n{retrieved_context}",
        max_tokens=400,
    )
