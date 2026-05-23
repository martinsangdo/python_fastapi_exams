"""
app/services/ai_service.py

Agentic AI features — Module 5 (Agentic AI + Prompt Engineering + RAG).

Demonstrates:
  - Prompt Engineering: system prompt design, structured output (JSON mode)
  - Function calling / Tool use: LLM calls Python tools
  - Streaming response: yield tokens as they arrive
  - Conversation history management
  - RAG pipeline: retrieve → augment → generate
  - Prompt injection detection (AI Security)
  - Cost optimisation: cache AI responses in Redis
"""
import json
from typing import AsyncIterator, Optional
import structlog

from app.core.config import settings
from app.core.cache import cache_get, cache_set, CacheKeys
from app.core.security import detect_prompt_injection
from app.core.database import get_db

log = structlog.get_logger()


# ─── Prompt Templates ─────────────────────────────────────────────────────────
# Module 5: Prompt Engineering — system prompt vs user prompt

HINT_SYSTEM_PROMPT = """You are an expert exam coach helping students prepare for certification exams.

RULES:
- Give a helpful hint that guides thinking WITHOUT revealing the direct answer.
- Keep hints under 100 words.
- Be encouraging and educational.
- If the student asks something unrelated to the exam question, redirect them politely.
- NEVER reveal which option is correct by letter (A, B, C...).

Respond ONLY with the hint text. No preamble."""

EXPLANATION_SYSTEM_PROMPT = """You are an expert exam coach.
After a student answers a question, explain WHY the correct answer is correct
and why the others are wrong. Be concise (max 150 words), educational, and clear.
Respond in structured JSON: {"explanation": "...", "key_concept": "...", "tip": "..."}"""

STUDY_ASSISTANT_SYSTEM_PROMPT = """You are an AI study assistant for exam preparation.
You have access to official exam documentation. Use it to give accurate, sourced answers.
If information is not in the provided context, say so honestly.
Keep answers concise, practical, and exam-focused."""


# ─── Tool Definitions (Function Calling) ─────────────────────────────────────
# Module 5: Function calling / Tool use — LLM decides which tool to invoke

STUDY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_exam_docs",
            "description": "Search the official exam documentation for relevant information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "exam_id": {"type": "string", "description": "Exam ID to search within"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_similar_questions",
            "description": "Find similar practice questions based on a topic or concept",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                },
                "required": ["topic"],
            },
        },
    },
]


# ─── Hint Generation ──────────────────────────────────────────────────────────

async def get_question_hint(question_id: str, user_question: str, user_id: str) -> str:
    """
    Generate a contextual hint for a question.
    Cached per user+question to save API cost (Module 2: Cache).
    Prompt injection guarded (Module 5: AI Security).
    """
    # Security: detect prompt injection before sending to LLM
    if detect_prompt_injection(user_question):
        log.warning("ai.prompt_injection_detected", user_id=user_id)
        return "I can only help with exam-related questions. Please ask about the question content."

    cache_key = CacheKeys.AI_HINT.format(question_id=question_id, user_id=user_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    from bson import ObjectId
    question = await db.questions.find_one({"_id": ObjectId(question_id)})
    if not question:
        return "Question not found."

    options_text = "\n".join(
        f"  {o['key']}. {o['text']}" for o in question["options"]
    )
    user_message = (
        f"Question: {question['text']}\n\nOptions:\n{options_text}\n\n"
        f"Student asks: {user_question}"
    )

    hint = await _call_llm(
        system=HINT_SYSTEM_PROMPT,
        user=user_message,
        max_tokens=150,
    )

    # Cache for 1 hour — same user shouldn't burn tokens on repeated requests
    await cache_set(cache_key, hint, ttl=3600)
    return hint


async def get_answer_explanation(question_id: str) -> dict:
    """
    Return structured explanation after answering — JSON mode output.
    Cached globally (not per-user) — same question, same explanation.
    """
    cache_key = CacheKeys.AI_EXPLAIN.format(question_id=question_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    from bson import ObjectId
    question = await db.questions.find_one({"_id": ObjectId(question_id)})
    if not question:
        return {"explanation": "", "key_concept": "", "tip": ""}

    options_text = "\n".join(
        f"  {o['key']}. {o['text']} {'✓' if o['is_correct'] else ''}"
        for o in question["options"]
    )
    user_message = (
        f"Question: {question['text']}\n\nOptions (✓ = correct):\n{options_text}\n\n"
        f"Domain explanation from study material: {question.get('explanation', 'N/A')}"
    )

    raw = await _call_llm(
        system=EXPLANATION_SYSTEM_PROMPT,
        user=user_message,
        max_tokens=300,
        json_mode=True,
    )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"explanation": raw, "key_concept": "", "tip": ""}

    await cache_set(cache_key, result, ttl=86400)  # explanations change rarely
    return result


# ─── Streaming Study Assistant ────────────────────────────────────────────────

async def study_assistant_stream(
    question: str,
    conversation_history: list[dict],
    exam_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Streaming AI study assistant with conversation history.
    Module 5: Streaming response + conversation history management.
    """
    if detect_prompt_injection(question):
        yield "I can only help with exam preparation topics."
        return

    # RAG: retrieve relevant context first
    context = ""
    if exam_id:
        context = await _retrieve_context(question, exam_id)

    system = STUDY_ASSISTANT_SYSTEM_PROMPT
    if context:
        system += f"\n\nRELEVANT DOCUMENTATION:\n{context}"

    # Build messages with history (Module 5: conversation history management)
    messages = [{"role": "system", "content": system}]
    for msg in conversation_history[-6:]:   # keep last 6 turns to control context window cost
        messages.append(msg)
    messages.append({"role": "user", "content": question})

    # Stream response
    async for token in _stream_llm(messages):
        yield token


async def agentic_study_session(
    task: str,
    exam_id: str,
    user_id: str,
) -> dict:
    """
    Agentic loop: LLM decides which tools to use to answer a study task.
    Module 5: Agent loop — observe → plan → act → reflect.
    """
    log.info("agent.session_start", task=task[:100], exam_id=exam_id)

    messages = [
        {"role": "system", "content": STUDY_ASSISTANT_SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    steps = []
    max_iterations = 5   # prevent infinite loops — Module 5: Agent safety

    for iteration in range(max_iterations):
        # Step: observe — get LLM response with tool options
        response = await _call_llm_with_tools(messages, STUDY_TOOLS)

        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])

                # Step: act — execute the chosen tool
                tool_result = await _execute_tool(tool_name, tool_args, exam_id)
                steps.append({"tool": tool_name, "args": tool_args, "result": tool_result})

                # Feed result back to LLM
                messages.append({"role": "assistant", "content": None, "tool_calls": response["tool_calls"]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result),
                })
        else:
            # Step: reflect — LLM has enough context, return final answer
            final_answer = response.get("content", "")
            log.info("agent.session_complete", iterations=iteration + 1, steps=len(steps))
            return {
                "answer": final_answer,
                "steps": steps,
                "iterations": iteration + 1,
            }

    return {"answer": "Could not complete the task within the step limit.", "steps": steps, "iterations": max_iterations}


# ─── RAG ──────────────────────────────────────────────────────────────────────

async def _retrieve_context(query: str, exam_id: str, top_k: int = 3) -> str:
    """
    RAG retrieval step — Module 5: RAG + Vector Database.
    In production: use ChromaDB or pgvector.
    """
    # Production implementation:
    # from langchain_openai import OpenAIEmbeddings
    # from langchain_community.vectorstores import Chroma
    #
    # embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
    # vectorstore = Chroma(
    #     collection_name=f"exam_{exam_id}",
    #     embedding_function=embeddings,
    #     persist_directory="./chroma_db",
    # )
    # docs = vectorstore.similarity_search(query, k=top_k)
    # return "\n\n".join(d.page_content for d in docs)

    # Demo: return empty context
    return ""


# ─── LLM Wrappers ─────────────────────────────────────────────────────────────

async def _call_llm(
    system: str,
    user: str,
    max_tokens: int = 500,
    json_mode: bool = False,
) -> str:
    """Single-turn LLM call using OpenAI-compatible API."""
    if not settings.OPENAI_API_KEY:
        return "[AI service not configured — set OPENAI_API_KEY]"

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        kwargs = dict(
            model=settings.AI_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
    except Exception as e:
        log.error("ai.llm_error", error=str(e))
        return f"AI temporarily unavailable: {str(e)}"


async def _stream_llm(messages: list[dict]) -> AsyncIterator[str]:
    """Streaming LLM response — Module 5: Streaming."""
    if not settings.OPENAI_API_KEY:
        yield "[AI service not configured — set OPENAI_API_KEY]"
        return

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=messages,
            max_tokens=settings.AI_MAX_TOKENS,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        log.error("ai.stream_error", error=str(e))
        yield f"\n[Stream error: {str(e)}]"


async def _call_llm_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    """LLM call with function calling support — Module 5: Tool use."""
    if not settings.OPENAI_API_KEY:
        return {"content": "[AI not configured]", "tool_calls": None}

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=settings.AI_MAX_TOKENS,
        )
        msg = resp.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None,
        }
    except Exception as e:
        log.error("ai.tool_call_error", error=str(e))
        return {"content": str(e), "tool_calls": None}


async def _execute_tool(tool_name: str, args: dict, exam_id: str) -> dict:
    """Dispatch tool calls from the agent — Module 5: Agent Loop."""
    if tool_name == "search_exam_docs":
        context = await _retrieve_context(args["query"], exam_id)
        return {"found": bool(context), "content": context[:1000]}

    elif tool_name == "get_similar_questions":
        db = get_db()
        query = {"exam_id": exam_id}
        if "difficulty" in args:
            query["difficulty"] = args["difficulty"]
        if "topic" in args:
            query["tags"] = {"$in": [args["topic"]]}
        cursor = db.questions.find(query, {"text": 1, "difficulty": 1}).limit(3)
        questions = [{"text": q["text"], "difficulty": q["difficulty"]} async for q in cursor]
        return {"questions": questions}

    return {"error": f"Unknown tool: {tool_name}"}
