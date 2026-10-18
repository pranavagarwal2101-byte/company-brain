# Design Decisions

A log of every significant design decision: what was decided, why, and which
alternatives were rejected. Read this before changing anything structural —
most "obvious improvements" were considered and rejected for a reason recorded
here.

**Other docs:** [README.md](README.md) · [ARCHITECTURE.md](ARCHITECTURE.md)
(how it works) · [TECH_PRD.md](TECH_PRD.md) (goals and constraints) ·
[STATE.md](STATE.md) (current status)

## How to add an entry

Append a new entry at the end with the next number. Never renumber or delete
entries; if a decision is reversed, set its status to
`Superseded by D-NNN` and add the new entry. Use this template:

```markdown
## D-NNN: Short title

- **Date:** YYYY-MM-DD
- **Status:** Accepted | Superseded by D-NNN | Proposed
- **Context:** What problem or constraint forced a choice.
- **Decision:** What we chose.
- **Alternatives rejected:** Each option, and why it lost.
- **Consequences:** What this makes easier, harder, or obligatory.
```

"Original design" means the decision predates the 2026-10-18 working session
in which the code was first run against a live database.

## Index

| # | Decision | Status |
|---|---|---|
| D-001 | Graph traversal, not RAG | Accepted |
| D-002 | `Decision` is a first-class node | Accepted |
| D-003 | Expertise is inferred, not stated | Accepted |
| D-004 | Every tool returns a path alongside the answer | Accepted |
| D-005 | Gemini picks from fixed tools and never writes Cypher | Accepted |
| D-006 | Never use `EXISTS { }` subqueries | Accepted (verified) |
| D-007 | No frontend | Accepted |
| D-008 | Small queries merged in Python, not one clever query | Accepted |
| D-009 | Topic matching by word stems with `any()` | Accepted |
| D-010 | Tickets reached through the decider's work; no `IMPLEMENTS` edge | Accepted |
| D-011 | Integers inlined with `int()` for `LIMIT` and path bounds | Accepted |
| D-012 | MERGE-based ingestion with clean-build and `--update` modes | Accepted |
| D-013 | Synthetic data only | Accepted |
| D-014 | FalkorDB Cloud rather than local Docker | Accepted |
| D-015 | `.env` loaded in `graph.py` | Accepted |
| D-016 | Gemini model choice: `gemini-3.8-flash` default | Accepted (revised) |
| D-017 | Pace requests, retry with backoff, isolate failures | Accepted |
| D-018 | The agent quotes paths verbatim | Accepted |
| D-019 | Fix DEC-005's dates by moving the incident, not the decision | Accepted |
| D-020 | `who_to_ask` ranks by kind of connection and uses edge notation | Accepted |
| D-021 | Every ingested node and edge type must be traversed | Accepted |

---

## D-001: Graph traversal, not RAG

- **Date:** Original design
- **Status:** Accepted
- **Context:** Track 03 asks for an agent that understands how a company
  works. The common approach is retrieval-augmented generation: embed
  documents, retrieve similar passages, let the LLM answer. The hackathon also
  disqualifies projects where the graph is decoration (Rule 3).
- **Decision:** All knowledge lives in a FalkorDB graph. Every agent tool is a
  Cypher traversal. There is no vector store, no embedding and no document
  retriever anywhere in the project.
- **Alternatives rejected:**
  - *RAG over documents:* answers "what text sounds related", not "what is
    connected". It cannot assemble a decision chain spread across documents,
    infer expertise, or follow transitive dependencies. It would also let the
    product work without FalkorDB, which fails Rule 3.
  - *Hybrid (graph + vector fallback):* the fallback would be what answers the
    hard questions in practice, making the graph decorative, and it weakens
    the explainability claim (a similarity score is not a path).
- **Consequences:** Questions must map onto one of the pre-written traversals;
  free-text questions outside them get "the graph has no record". Topic
  matching is keyword-based (D-009). Removing FalkorDB breaks the product
  completely — which is the point.

## D-002: `Decision` is a first-class node

- **Date:** Original design
- **Status:** Accepted
- **Context:** Most knowledge graphs link documents to entities. The most
  valuable question in an engineering org is "why do we do it this way?", and
  the answer is a decision with a history.
- **Decision:** Model decisions as nodes with `statement`, `made_at` and
  `status`, connected by `ABOUT` (system), `TRIGGERED_BY` (incident),
  `JUSTIFIED_BY` (documents), `SUPERSEDES` (older decision) and `DECIDED`
  (person).
- **Alternatives rejected:**
  - *Decisions as properties of documents (e.g. an RFC's "outcome"):* loses
    supersession history and the link to the triggering incident; one RFC can
    justify several decisions.
  - *Decisions only as text inside documents:* not traversable at all.
- **Consequences:** "Why is the retry limit three, and what was it before?"
  becomes a traversal (DEC-001 → INC-212, RFC-47, SUPERSEDES DEC-000). Decisions
  must be recorded explicitly in the source data.

## D-003: Expertise is inferred, not stated

- **Date:** Original design
- **Status:** Accepted
- **Context:** "Who knows this system?" is different from "who owns it". Skills
  lists and profiles are stale or missing in real organisations.
- **Decision:** Never store expertise. Derive it at query time from
  `(Person)-[:WORKED_ON {commits}]->(Project)-[:USES]->(System)` (summing commits)
  plus `(Person)-[:PARTICIPATED_IN]->(Incident)-[:AFFECTED]->(System)`.
- **Alternatives rejected:**
  - *An `EXPERT_IN` edge or skills property:* would be one more stated fact to
    keep current, and turns the most graph-native question into a lookup.
  - *A single blended score:* hides which kind of knowledge a person has;
    building a system (commits) and running it under pressure (incidents) are
    returned as separate lists.
- **Consequences:** The headline result — Aman Gupta (107 commits) out-knows
  owner Riya Sharma (48) on payments-service, and two Growth-team engineers
  surface — exists in no record. Commit counts are a crude signal; recency
  weighting is future work.

## D-004: Every tool returns a path alongside the answer

- **Date:** Original design
- **Status:** Accepted
- **Context:** Track 03 asks for "answers with clear sources". LLM answers
  without provenance cannot be trusted or checked.
- **Decision:** Every tool returns `{"answer": ..., "path": ...}`. The path is
  built only from rows the Cypher query returned, in
  `(Label:value)-[:REL]->(Label:value)` notation. The agent must show it, and
  `agent.py` also prints every path itself after each answer.
- **Alternatives rejected:**
  - *Citing documents only:* a document list does not show how they connect.
  - *Asking the LLM to explain its reasoning:* that is a description, not
    evidence; it can be invented.
- **Consequences:** Retrieval and explanation are the same object — the agent
  cannot cite a path it did not walk. Paths can be long (trace_decision); this
  is accepted. See D-018 for verbatim quoting.

## D-005: Gemini picks from fixed tools and never writes Cypher

- **Date:** Original design
- **Status:** Accepted
- **Context:** LLMs can generate Cypher ("text-to-Cypher"), which is flexible.
- **Decision:** Gemini only sees five function declarations and chooses which
  to call with what arguments. It never sees the schema, the data or any
  Cypher. All Cypher is written and reviewed by hand in `tools.py`.
- **Alternatives rejected:**
  - *Text-to-Cypher:* generated queries can be wrong, slow, or (with write
    clauses) destructive; they cannot be reviewed in advance; and the team
    could not explain to judges a query they did not write (Rule 12). The
    shown path would describe an unreviewed query.
  - *Text-to-Cypher with validation:* adds complexity without solving
    explainability.
- **Consequences:** Coverage is limited to five question shapes. Every query is
  explainable clause by clause, parameterised, and documented verbatim in the
  README. Adding a capability means adding a tool.

## D-006: Never use `EXISTS { }` subqueries

- **Date:** 2026-10-18 (verified)
- **Status:** Accepted
- **Context:** The original code avoided `EXISTS { MATCH ... }` and `UNION` on
  the suspicion that FalkorDB might not support them; nothing had run against
  a real instance.
- **Decision:** Tested on the live FalkorDB 4.22 instance. `EXISTS { MATCH ...
  }` fails with a parse error, and `exists((a)-[:R]->(b))` fails with "Unable
  to resolve filtered alias". Never use either. Where an existence check is
  needed, use a bare pattern predicate, `WHERE (a)-[:R]->(b)` or
  `WHERE NOT (a)-[:R]->(b)`, which both work. `UNION` **does** work and is
  allowed, but see D-008.
- **Alternatives rejected:** Keeping the old README claim "FalkorDB has no
  UNION" — it was false, and the judges are FalkorDB people.
- **Consequences:** Recorded in `CLAUDE.md` as a hard rule.

## D-007: No frontend

- **Date:** Original design
- **Status:** Accepted
- **Context:** A web UI is common in hackathon demos. Time was limited, and the
  rules accept complete local setup instructions plus a demo video in place of
  a live deployment.
- **Decision:** Command-line interface only (`agent.py --demo`, single
  question, interactive). Visual graph exploration uses FalkorDB's own browser
  (Cloud console, or `localhost:3000` with Docker).
- **Alternatives rejected:**
  - *Web chat UI:* time spent on UI is time not spent on the graph, which is
    what is judged; it would also hide the tool call and raw path that the
    terminal shows naturally.
  - *Custom graph visualisation:* duplicates FalkorDB's browser.
- **Consequences:** The terminal output is the demo: tool chosen (`→ tool(...)`),
  answer, "How I know this:", and "graph traversals executed".

## D-008: Small queries merged in Python, not one clever query

- **Date:** Original design; reaffirmed 2026-10-18
- **Status:** Accepted
- **Context:** Several tools combine different edge types (who_to_ask uses
  three; trace_decision needs decision, documents, tickets and citations).
  These could be single large queries with `UNION`, `CALL` subqueries or
  chained `OPTIONAL MATCH`es.
- **Decision:** One small query per concern, merged in Python by key (person
  email or decision id). Ingestion likewise splits `MERGE ... WITH ... MATCH`
  chains into separate statements.
- **Alternatives rejected:**
  - *`UNION` for who_to_ask:* works on FalkorDB 4.22 (D-006), but the merged
    query is harder to read and explain, and the legs return different columns.
  - *One large trace_decision query:* multiple `OPTIONAL MATCH`es multiply rows
    (decision × docs × tickets × citations) and are hard to debug.
- **Consequences:** More round-trips (up to 4 per tool) — negligible at this
  scale. Each query can be explained in isolation, and a failure points at one
  leg.

## D-009: Topic matching by word stems with `any()`

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** `trace_decision` originally matched the whole topic string with
  `CONTAINS`. "retry" did not match "retries", so the headline demo question
  returned nothing; multi-word topics like "settlement retry limit" also
  failed.
- **Decision:** `_search_terms()` in Python splits the topic into words, drops
  stopwords and words under 3 letters, keeps hyphenated names whole, and strips
  one suffix (`ies`, `es`, `s`, `y`). Cypher keeps a record if **any** term
  matches: `WHERE any(term IN $terms WHERE toLower(x) CONTAINS term)`. Results
  are ranked by how many terms matched. Applied to `trace_decision` and
  `who_to_ask`.
- **Alternatives rejected:**
  - *Require all terms:* long questions fail (no statement contains "limit").
  - *Full-text index:* more machinery to explain and test on deadline day.
  - *Embeddings / semantic matching:* violates D-001.
  - *One query per term merged in Python:* the planned fallback if `any()`
    failed; unnecessary once `any()` was verified on the live engine.
- **Consequences:** Simple and explainable, but crude: no handling of "-ing" or
  "-ed"; substring matching can over-match generic words like "service".

## D-010: Tickets reached through the decider's work; no `IMPLEMENTS` edge

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** Ticket nodes and the `REPORTED`, `PART_OF` and `REFERENCES` edges
  were ingested but never traversed — decoration (D-021). There is no direct
  Decision → Project or Ticket → Decision edge.
- **Decision:** In `trace_decision`, find tickets on projects that **use the
  decision's system and that the person who made the decision worked on**:
  `(decider)-[:DECIDED]->(d)-[:ABOUT]->(:System)<-[:USES]-(pr)`,
  `(decider)-[:WORKED_ON]->(pr)`, `(t:Ticket)-[:PART_OF]->(pr)`. Only for
  `active` decisions (a superseded decision's follow-up work belongs to its
  replacement). Separately, return documents that `REFERENCES` a justifying
  document, excluding documents that are themselves justifications.
- **Alternatives rejected:**
  - *Route through the system only:* too broad — the retry decision would list
    unrelated idempotency and notification tickets.
  - *Route through the justifying document's author:* four hops with weak
    meaning ("the RFC author also worked on X").
  - *Add a `(Ticket)-[:IMPLEMENTS]->(Decision)` edge:* exact, but adds an edge
    type to explain for a small gain. Explicitly declined by the project
    owner.
- **Consequences:** Precise for 5 of 6 decisions (DEC-001 → PAY-1042, PAY-1043).
  Imprecise for DEC-002: its decider worked on all three payments-service
  projects, so it also lists PAY-1042, PAY-1043 and GRW-0311. Known and
  accepted ([STATE.md](STATE.md#known-issues)).

## D-011: Integers inlined with `int()` for `LIMIT` and path bounds

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** Cypher does not accept parameters in variable-length bounds
  (`*1..$n`). `LIMIT $limit` broke when Gemini sent `5.0`.
- **Decision:** Inline these two values into the query text after forcing them
  through `int()` (`LIMIT {max(1, int(limit))}`, `*1..{int(max_depth)}`). All
  other inputs stay `$parameters`.
- **Alternatives rejected:** Parameterised `LIMIT` (float breakage); string
  formatting without `int()` (Cypher injection risk).
- **Consequences:** Rule in `CLAUDE.md`: sanitise any interpolated value.

## D-012: MERGE-based ingestion with clean-build and `--update` modes

- **Date:** Original design (MERGE); `--update` added 2026-10-18
- **Status:** Accepted
- **Context:** Track 03 lists "keeping knowledge current as things change".
- **Decision:** Every write is a `MERGE` on the node's key, followed by `SET`
  for properties. `python ingest.py` wipes the graph then loads (clean demo
  build). `python ingest.py --update` loads on top of the live graph without
  wiping or recreating indexes.
- **Alternatives rejected:** `CREATE`-based loading (duplicates on re-run);
  claiming idempotency from two wiped runs (proves nothing — the wipe hides
  duplicates).
- **Consequences:** Verified live: a no-wipe re-load leaves all 62 nodes and
  139 relationships unchanged, and a changed ticket status is picked up.
  Deletions are not propagated (future work).

## D-013: Synthetic data only

- **Date:** Original design
- **Status:** Accepted
- **Context:** Hackathon Rule 6 forbids private, personal or restricted data;
  Track 03 makes real company data tempting.
- **Decision:** `company.json` describes a fictional company ("Acme"),
  hand-written so the interesting questions require multi-hop traversal.
- **Alternatives rejected:** Public open-source project data (messier, weaker
  decision records, consent questions about people).
- **Consequences:** The data is small (62 nodes) and curated; results are
  illustrative, not evidence about real organisations.

## D-014: FalkorDB Cloud rather than local Docker

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** The README originally assumed local Docker. The development
  machine (Windows 11) has neither Docker nor WSL, and installing them needs
  admin rights and likely a reboot on deadline day.
- **Decision:** Use a free FalkorDB Cloud instance. `graph.py` accepts
  optional `FALKORDB_USERNAME`, `FALKORDB_PASSWORD` and `FALKORDB_SSL`. Local
  Docker remains documented for judges.
- **Alternatives rejected:** Installing Docker Desktop (30+ minutes, reboot
  risk).
- **Consequences:** `FALKORDB_SSL=false` works on our instance; `true` hung on
  connect. The local Docker path is documented but untested.

## D-015: `.env` loaded in `graph.py`

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** Only `agent.py` called `load_dotenv()`, and only after `graph.py`
  had already been imported (via `tools`). `ingest.py` never loaded `.env`.
  Connection settings in `.env` were silently ignored.
- **Decision:** Call `load_dotenv()` at the top of `graph.py`, the module every
  entry point imports first.
- **Consequences:** `ingest.py`, `tools.py` and `agent.py` all see the same
  configuration.

## D-016: Gemini model choice

- **Date:** 2026-10-18
- **Status:** Accepted (revised twice the same day)
- **Context:** The original default `gemini-2.5-flash` returned 404 ("no longer
  available to new users").
- **Decision:** The committed default is `gemini-3.8-flash`, overridable with
  `GEMINI_MODEL`. History: 2.5-flash → 3.8-flash (full 5/5 demo run); briefly
  3.7-flash in `agent.py` after 3.8's daily quota ran out; then back to
  3.8-flash, because the default must suit a judge with a fresh key, not the
  developer's remaining quota. The developer's own `.env` overrides to
  3.7-flash for the 18 Oct recording only.
- **Alternatives rejected:**
  - *Leaving the model as a manual override:* a judge cloning the repo must
    get a working default.
  - *Defaulting to 3.7-flash:* it had quota tonight, but an older model is
    more likely to be retired for new keys, and it had only one verified
    question.
  - *`gemini-flash-latest` alias:* tracks new releases automatically, but its
    behaviour could change under us and it was never tested.
- **Consequences:** See [STATE.md](STATE.md#gemini) for which model each doc
  currently names — keep `agent.py`, `.env.example` and the README in sync.

## D-017: Pace requests, retry with backoff, isolate failures

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** The free tier allows 5 requests/minute. A demo run makes about
  11 requests and crashed with a traceback on question 4. The demo is what
  gets recorded for the submission video.
- **Decision:** Three layers in `agent.py`: (1) **pacing** — every call waits
  until `60 / GEMINI_REQUESTS_PER_MINUTE + 1` seconds (13 s) have passed since
  the previous one; (2) **retry** — on 429 or 5xx, wait Gemini's suggested
  `retryDelay` (or 10/20/40/80 s), up to 4 retries, but give up at once if the
  suggested wait exceeds 90 s (daily quota) or the error is not retryable;
  (3) **isolation** — `answer_question()` reports a failed question and moves on.
- **Alternatives rejected:** A fixed 60 s pause between questions (always slow,
  even on paid keys); retry only (still hits the limit, noisier).
- **Consequences:** A full demo takes about 2–3 minutes. Verified: offline tests
  of each path, and a live 503 retried successfully mid-demo. Does not help
  with the 20 requests/day limit.

## D-018: The agent quotes paths verbatim

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** In one demo answer Gemini rewrote the path in its own Cypher-like
  style. Rewording means the agent is *describing* the traversal rather than
  *quoting* it, which undermines the D-004 claim.
- **Decision:** System prompt rule 3 requires copying each tool's `path`
  "exactly as given, character for character, inside a code block… a
  quotation of the traversal that ran, not a description of it".
- **Consequences:** Verified on `gemini-3.7-flash` for one question (exact
  match). A full five-question verbatim check is still open
  ([STATE.md](STATE.md)).

## D-019: Fix DEC-005's dates by moving the incident, not the decision

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** DEC-005 (made 2024-08-10) was `TRIGGERED_BY` INC-301 dated
  2024-11-19 — a decision predating its own trigger.
- **Decision:** Moved INC-301 to 2024-07-22, giving the order incident →
  RFC-33 (2024-08-05) → DEC-005 (2024-08-10) → ticket PLT-0455 (2024-08-14).
  All decisions were re-checked by script: every trigger precedes its decision,
  and every justifying document falls between its incident and its decision.
- **Alternatives rejected:** Moving the decision to November (it would then
  follow its own RFC and implementation ticket by months).

## D-020: `who_to_ask` ranks by kind of connection and uses edge notation

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** `who_to_ask` combines three edge types; its path was prose
  ("owns X; wrote Y") while the other four tools used edge notation.
- **Decision:** Rank owner (1) > author (2) > contributor (3), then by number of
  reasons. Paths use `-[:EDGE]->` notation; a project returned once per system
  it uses is folded into one edge, e.g. `(System:audit-log/ledger-db)`.
- **Alternatives rejected:** Ranking by commit volume (that is `find_experts`'
  job; the tools answer different questions).
- **Consequences:** Two contributors at the same rank are not ordered by
  commits — expected, and worth explaining to judges.

## D-021: Every ingested node and edge type must be traversed

- **Date:** 2026-10-18
- **Status:** Accepted
- **Context:** Rule 3 (decoration). A judge could point at ingested-but-unused
  data as graph built for show.
- **Decision:** Keep an edge-coverage check: every label and relationship type
  in `company.json` must be read by at least one tool. If data cannot be made
  useful, remove it from the dataset rather than leave it unused.
- **Consequences:** Met as of 2026-10-18 (table in
  [ARCHITECTURE.md](ARCHITECTURE.md#53-edge-coverage)). Some *properties* are
  stored but not read (see [STATE.md](STATE.md#known-issues)); properties are
  attributes, not structure, and were judged acceptable.
