"""Company Brain — a graph-grounded agent over FalkorDB, driven by Gemini.

The model never sees the graph directly. It chooses a traversal, the traversal
runs as Cypher against FalkorDB, and the rows plus the path that produced them
come back. Every answer is therefore grounded in edges that were actually
walked, and the path is shown alongside the answer.

Usage:
    python agent.py                      # interactive
    python agent.py "who owns payments-service?"
    python agent.py --demo               # run the scripted demo questions
"""

import os
import re
import sys
import textwrap
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from tools import TOOLS

load_dotenv()

# gemini-2.5-flash is no longer offered to new API keys (it returns 404).
# 3.8-flash is the newest Flash model, so the least likely to be retired.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Gemini's free tier allows 5 requests per minute per model. Requests are
# spaced 60/RPM seconds apart, plus one second of margin, so a free-tier key
# never trips the limit. Raise GEMINI_REQUESTS_PER_MINUTE on a paid key.
REQUESTS_PER_MINUTE = int(os.getenv("GEMINI_REQUESTS_PER_MINUTE", "5"))
MIN_SECONDS_BETWEEN_REQUESTS = 60 / REQUESTS_PER_MINUTE + 1
MAX_RETRIES = 4        # per request, on 429 (rate limit) or 5xx (overloaded)
MAX_WAIT_SECONDS = 90  # a longer suggested wait usually means the daily quota is gone

SYSTEM_PROMPT = """\
You are Company Brain, an assistant that answers questions about how an
engineering organisation works. Your knowledge comes only from a FalkorDB
knowledge graph, which you reach through the provided tools.

Rules:
1. Never answer from your own assumptions. If a tool returns nothing, say the
   graph has no record of it. Do not invent people, systems or decisions.
2. Always call at least one tool before answering a question about the company.
3. Every tool result includes a "path" field describing the relationships that
   were traversed. After your answer, add a section headed
   "How I know this:" and copy each tool's "path" value into it exactly as
   given, character for character, inside a code block. Do not reword,
   reformat, split, shorten or reorder it: it is a quotation of the traversal
   that ran, not a description of it. After the paths you may list document
   ids or URLs.
4. When a decision supersedes an earlier one, say what changed and why.
5. Be concise. Lead with the answer, then the evidence.
"""

# --- Tool schemas exposed to Gemini ----------------------------------------

FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="find_owner",
        description=(
            "Find who formally owns a system or service, and the team they are on. "
            "Use for questions like 'who owns X' or 'who is responsible for X'."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "system": types.Schema(
                    type=types.Type.STRING,
                    description="Exact system name, e.g. 'payments-service', 'ledger-db'.",
                )
            },
            required=["system"],
        ),
    ),
    types.FunctionDeclaration(
        name="find_experts",
        description=(
            "Find who has hands-on experience with a system, derived by traversing "
            "Person->Project->System contributions and incident participation. "
            "Use for 'who knows about X', 'who should review a change to X', "
            "'who has worked on X before'. This is different from ownership."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "system": types.Schema(
                    type=types.Type.STRING,
                    description="Exact system name, e.g. 'payments-service'.",
                ),
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description="Maximum number of people to return. Default 5.",
                ),
            },
            required=["system"],
        ),
    ),
    types.FunctionDeclaration(
        name="trace_decision",
        description=(
            "Trace a technical decision back to the incident that triggered it and "
            "the documents that justify it, including any decision it replaced. "
            "Use for 'why do we do X this way', 'why is the retry limit three', "
            "'what changed about X'."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "topic": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "A few keywords. Each word is matched, ignoring plurals, "
                        "against decision statements and system names, and decisions "
                        "matching more words rank first. Examples: 'retry', "
                        "'settlement retry limit', 'idempotency keys', "
                        "'payments-service', 'audit events'."
                    ),
                )
            },
            required=["topic"],
        ),
    ),
    types.FunctionDeclaration(
        name="blast_radius",
        description=(
            "Find everything that breaks if a system goes down, by following "
            "DEPENDS_ON edges transitively, up to 4 hops by default. Use for "
            "'what breaks if X "
            "goes down', 'what depends on X', 'impact of X failing'."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "system": types.Schema(
                    type=types.Type.STRING,
                    description="Exact system name, e.g. 'auth-service'.",
                ),
                "max_depth": types.Schema(
                    type=types.Type.INTEGER,
                    description="Maximum dependency hops to follow. Default 4.",
                ),
            },
            required=["system"],
        ),
    ),
    types.FunctionDeclaration(
        name="who_to_ask",
        description=(
            "Find the right person to ask about a topic, combining ownership, "
            "document authorship and project contributions. Use when the question "
            "is about a broad topic rather than one named system."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "topic": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "A few keywords. Each word is matched, ignoring plurals, "
                        "e.g. 'retry', 'auth', 'audit events'."
                    ),
                )
            },
            required=["topic"],
        ),
    ),
]


def build_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is not set. Put it in a .env file:")
        print('  echo "GEMINI_API_KEY=your-key" > .env')
        sys.exit(1)
    return genai.Client(api_key=api_key)


# --- Pacing and retry around every Gemini call -----------------------------

_last_request_at = 0.0


def _wait_for_slot():
    """Sleep just long enough to keep requests MIN_SECONDS_BETWEEN_REQUESTS apart."""
    global _last_request_at
    wait = _last_request_at + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _suggested_delay(exc):
    """Gemini's 429 body says how long to wait, e.g. "retryDelay": "23s"."""
    match = re.search(r"'retryDelay': '([\d.]+)s'", str(exc.details))
    return float(match.group(1)) + 1 if match else None


def generate(client, contents, config):
    """generate_content, paced to the rate limit and retried on 429 / 5xx.

    Waits Gemini's suggested delay when it gives one, otherwise backs off
    10s, 20s, 40s, 80s. Anything else (bad key, unknown model) raises at once.
    """
    for attempt in range(MAX_RETRIES + 1):
        _wait_for_slot()
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except errors.APIError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == MAX_RETRIES:
                raise
            delay = _suggested_delay(exc) or 10 * 2 ** attempt
            if delay > MAX_WAIT_SECONDS:
                raise
            print(f"  ... Gemini returned {exc.code}, waiting {delay:.0f}s "
                  f"(retry {attempt + 1}/{MAX_RETRIES})")
            time.sleep(delay)


def ask(client, question, verbose=True):
    """Run one question through the tool-calling loop."""
    contents = [
        types.Content(role="user", parts=[types.Part(text=question)])
    ]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
        temperature=0,
    )

    traversals = []

    for _ in range(6):  # bounded so a confused model cannot loop forever
        response = generate(client, contents, config)

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not calls:
            text = "".join(p.text for p in parts if getattr(p, "text", None))
            return text.strip(), traversals

        contents.append(candidate.content)

        response_parts = []
        for call in calls:
            name = call.name
            args = dict(call.args or {})
            fn = TOOLS.get(name)

            if verbose:
                pretty = ", ".join(f"{k}={v!r}" for k, v in args.items())
                print(f"  → {name}({pretty})")

            if fn is None:
                result = {"error": f"Unknown tool {name}"}
            else:
                try:
                    result = fn(**args)
                except Exception as exc:  # surface the error to the model
                    result = {"error": f"{type(exc).__name__}: {exc}"}

            if isinstance(result, dict) and "path" in result:
                traversals.append({"tool": name, "args": args, "path": result["path"]})

            response_parts.append(
                types.Part.from_function_response(name=name, response={"result": result})
            )

        contents.append(types.Content(role="user", parts=response_parts))

    return "Stopped after too many tool calls without reaching an answer.", traversals


DEMO_QUESTIONS = [
    "Who owns payments-service?",
    "Why is the settlement retry limit three? What was it before, and what changed it?",
    "What breaks if auth-service goes down?",
    "Who should review a change to payments-service, and why them?",
    "Who should I ask about how audit events are written?",
]


def print_answer(question, answer, traversals):
    print("\n" + "=" * 72)
    print(f"Q: {question}")
    print("=" * 72)
    print(textwrap.fill(answer, 72) if "\n" not in answer else answer)
    if traversals:
        print("\n--- graph traversals executed ---")
        for t in traversals:
            print(f"  [{t['tool']}] {t['path']}")


def answer_question(client, question):
    """Ask and print one question. A failure is reported, not raised, so one
    bad question cannot take down a demo run or the interactive session."""
    try:
        answer, traversals = ask(client, question)
    except Exception as exc:
        print(f"\n[!] Could not answer: {question}")
        print(f"    {type(exc).__name__}: {exc}")
        return False
    print_answer(question, answer, traversals)
    return True


def main():
    args = sys.argv[1:]
    client = build_client()

    if args and args[0] == "--demo":
        print(f"Model: {MODEL}, paced to {REQUESTS_PER_MINUTE} requests/minute")
        started = time.monotonic()
        answered = 0
        for q in DEMO_QUESTIONS:
            print(f"\n> {q}")
            answered += answer_question(client, q)
        minutes, seconds = divmod(round(time.monotonic() - started), 60)
        print(f"\nDemo finished: {answered}/{len(DEMO_QUESTIONS)} questions answered "
              f"in {minutes}m {seconds}s.")
        return

    if args:
        answer_question(client, " ".join(args))
        return

    print("Company Brain — graph-grounded agent over FalkorDB")
    print("Ask a question, or Ctrl-C to quit.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue
        if question in {"exit", "quit"}:
            return
        answer_question(client, question)


if __name__ == "__main__":
    main()
