# Technical PRD — Company Brain

What we are building, for whom, under which constraints, and what is
deliberately out of scope.

**Other docs:** [README.md](README.md) (entry point and setup) ·
[ARCHITECTURE.md](ARCHITECTURE.md) (how it works) ·
[DECISIONS.md](DECISIONS.md) (why it works that way) ·
[STATE.md](STATE.md) (current status and open items)

---

## 1. Context

Company Brain is a submission to **Graph Hacks 2026** (WeMakeDevs × FalkorDB),
**Track 03: Company Brain**. The hackathon ran 15–18 October 2026; submissions
closed **18 October 2026, 11:59 PM IST**.

Track 03's brief: *"Build an agent that understands how a company works.
Connect people, teams, projects, documents, and decisions in one graph, so the
agent can answer questions and get work done across all of it."* Its listed
focus areas:

1. Knowledge from docs, tickets, and chats in one graph
2. Who owns what, and who knows what
3. Tracing decisions back to their source
4. Keeping knowledge current as things change
5. Answers with clear sources

## 2. Problem

In an engineering organisation, the most useful answers are spread across
many records that were written separately and never linked:

- **"Why do we do it this way?"** The answer is a chain — a decision, the
  incident that caused it, the RFC and postmortem that justify it, the ticket
  that implemented it, and the older decision it replaced. No single document
  holds the chain.
- **"Who actually knows this system?"** The org chart says who *owns* it. Who
  has *worked on* it — across teams — is only visible by joining contribution
  and incident records.
- **"What breaks if this goes down?"** Requires following dependencies
  transitively; the affected systems' own documentation never mentions it.

Document search (keyword or vector/RAG) returns passages that *sound*
relevant. It cannot follow relationships, so it cannot assemble these chains,
and it cannot show how an answer was derived.

## 3. Users

| User | Typical question | Tool that answers it |
|---|---|---|
| Engineer new to a codebase | "Why is the retry limit three?" | `trace_decision` |
| Author of a change looking for a reviewer | "Who should review a change to payments-service?" | `find_experts` (+ `find_owner`) |
| On-call engineer | "What breaks if auth-service goes down, and whom do I page?" | `blast_radius` |
| Anyone with a broad question | "Who should I ask about audit events?" | `who_to_ask` |
| Engineering manager | "Is knowledge of this system concentrated in one person?" | `find_experts`, `who_to_ask` |

For the hackathon, the immediate audience is the **judges**, who must be able
to see that the graph does the work and that every answer is sourced.

## 4. Goals

- **G1 — Graph-native answers.** Every answer is produced by traversing a
  FalkorDB graph; the graph is the product, not a visualisation of it.
- **G2 — Answers nobody wrote down.** At least some questions must be
  answerable *only* by multi-hop traversal (inferred expertise, transitive
  impact, decision provenance).
- **G3 — Explainability by construction.** Every answer carries the exact
  traversal that produced it, quoted verbatim.
- **G4 — Explainable to a human.** The team must be able to explain the graph
  model, every query and the architecture to judges (hackathon Rule 12).
  Clarity beats cleverness throughout.
- **G5 — Reproducible by a judge.** Clone, configure `.env`, run two commands.

## 5. Non-goals (and why)

| Non-goal | Why |
|---|---|
| **No vector store, no embeddings, no document retriever.** | Hackathon Rule 3 disqualifies projects where the graph is decoration. A retriever would let the product answer without FalkorDB, and it would answer "what text sounds related" rather than "what is connected". It would also blur the explainability claim: a similarity score is not a path. |
| **No LLM-written Cypher (no text-to-Cypher).** | Generated queries can be wrong, unsafe or unexplainable, and the path shown would describe a query nobody reviewed. A fixed set of reviewed traversals is safer and fully explainable. See [DECISIONS.md](DECISIONS.md) D-005. |
| **No frontend.** | Time-boxed hackathon; the terminal output already shows the tool chosen, the answer and the raw path; FalkorDB's own browser covers visual exploration. See D-007. |
| **No real company data.** | Hackathon Rule 6 forbids private, personal or restricted data. All data is synthetic. |
| **No write actions ("get work done").** | Track 03 mentions getting work done; this project focuses on understanding. Acting (e.g. filing tickets) is future work. |
| **No chat ingestion.** | Not built in the time available; listed as future work and stated honestly in the README. |

## 6. Requirements

### 6.1 Functional

| ID | Requirement | Status |
|---|---|---|
| FR-1 | Load a company dataset into FalkorDB as a typed property graph (8 node labels, 16 relationship types). | Built |
| FR-2 | Re-loading the dataset must update the graph in place without duplicates (`ingest.py --update`). | Built, verified |
| FR-3 | Answer "who owns X" (stated ownership). | Built (`find_owner`) |
| FR-4 | Answer "who knows X" by inference from contributions and incidents. | Built (`find_experts`) |
| FR-5 | Trace a decision to its incident, justifying and citing documents, implementing tickets and superseded decision. | Built (`trace_decision`) |
| FR-6 | Compute transitive impact of a system failure, with hop distance and owners. | Built (`blast_radius`) |
| FR-7 | Rank people for a broad topic across ownership, authorship and contribution. | Built (`who_to_ask`) |
| FR-8 | Every tool returns `{answer, path}`; the agent quotes the path verbatim under "How I know this:". | Built |
| FR-9 | Natural-language topics must match despite plurals ("retry" finds "retries"). | Built (stem + `any()` matching) |
| FR-10 | A scripted demo (`agent.py --demo`) must complete on a free-tier Gemini key without crashing. | Built (pacing + retry + per-question isolation) |
| FR-11 | Every ingested node label and relationship type is traversed by at least one tool. | Met — see [ARCHITECTURE.md](ARCHITECTURE.md#53-edge-coverage) |

### 6.2 Non-functional

- **Explainability:** paths are built only from returned rows; the agent also
  prints the raw traversals itself, independent of the model.
- **Determinism:** `temperature=0`; tools are deterministic Cypher.
- **Safety of queries:** user/model input reaches Cypher only as `$parameters`;
  the two values inlined into query text (`LIMIT`, variable-length bound) are
  forced through `int()`.
- **Secrets:** real credentials only in `.env` (gitignored). `.env.example`
  holds placeholders.
- **Cost / quota:** must work on Gemini's free tier (5 requests/minute and 20
  requests/day per model, as observed on 2026-10-18).

### 6.3 Constraints — hackathon rules that shape the design

From the rules page (rule numbers as published):

- **Rule 2:** FalkorDB must be the primary graph database and support a
  central part of the product.
- **Rule 3:** *"if the product still works once FalkorDB is taken out, the
  graph is decoration"* — disqualifying.
- **Rule 6:** only public, synthetic or own data; nothing private, personal,
  login-protected or restricted.
- **Rule 8:** main coding must start after the hackathon starts.
- **Rule 10:** submission must include a public repo, a README with setup
  instructions **and the graph data model**, the Cypher queries the product
  depends on, a demo video, a live deployment *or* complete local setup
  instructions, and the track entered.
- **Rules 11–13:** AI coding assistants allowed but must be disclosed; the
  team must be able to explain the graph model, queries, architecture and
  decisions; fully AI-generated projects without understanding may be
  rejected.
- **Team:** solo or up to 4 members.

Technical constraints discovered during the build:

- FalkorDB 4.22 rejects `EXISTS { MATCH ... }` subqueries (see
  [ARCHITECTURE.md](ARCHITECTURE.md#7-falkordb-facts-this-design-relies-on)).
- The development machine has no Docker or WSL, so FalkorDB Cloud is used.
- `gemini-2.5-flash` is no longer available to new API keys.

## 7. Scope

### 7.1 Built

- Synthetic dataset (`company.json`) designed so the interesting questions
  need multi-hop traversal.
- MERGE-based ingestion with clean-build and `--update` modes.
- Five Cypher-backed tools returning answer + path.
- Gemini tool-calling agent with verbatim-path rule, request pacing, retry
  with backoff, and failure isolation; CLI with `--demo`, single-question and
  interactive modes.
- README with data model, all 12 Cypher queries (kept identical to the code),
  Track 03 mapping and setup for FalkorDB Cloud or local Docker.
- Deeper docs: this file, [ARCHITECTURE.md](ARCHITECTURE.md),
  [DECISIONS.md](DECISIONS.md), [STATE.md](STATE.md).

### 7.2 Deliberately not built

- `(Ticket)-[:IMPLEMENTS]->(Decision)` edge — would make ticket lookup exact,
  but adds an edge type to explain for a small gain (D-010).
- Frontend / web deployment (D-007).
- Text-to-Cypher (D-005).
- Vector search of any kind (D-001).

### 7.3 Future work

- **Chat ingestion:** `Message` nodes linked to the people, systems and
  decisions they mention (Track 03 focus area 1).
- **Deletions on re-ingest:** `--update` adds and updates but never removes
  records deleted from the source.
- **Live sources:** ingest from real trackers/wikis (with permission) instead
  of a static JSON file.
- **Recency weighting** for inferred expertise.
- **Actions:** let the agent file tickets or page owners (Track 03 "get work
  done").

## 8. Success criteria

The five demo questions in `agent.py` (`DEMO_QUESTIONS`) must each be answered
correctly by the right tool, with a verbatim "How I know this:" section:

1. Who owns payments-service? → `find_owner`
2. Why is the settlement retry limit three? → `trace_decision` (DEC-001,
   INC-212, RFC-47, PAY-1042, supersedes DEC-000)
3. What breaks if auth-service goes down? → `blast_radius` (api-gateway 1,
   payments-service 1, notification-service 2)
4. Who should review a change to payments-service? → `find_experts`
   (Aman 107 > Riya 48) and `find_owner`
5. Who should I ask about how audit events are written? → `who_to_ask`
   (Leila, then Victor and Grace)

Current status against these criteria is tracked in [STATE.md](STATE.md).
