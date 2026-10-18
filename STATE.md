# Project State

Where the project stands right now: what works, what has been verified against
the live database, what has never been tested, how the environment is set up,
and what is still open. **Update this file whenever any of that changes.**

**Last updated:** 2026-10-18, ~20:30 IST (deadline: 2026-10-18, 11:59 PM IST)

**Other docs:** [README.md](README.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[TECH_PRD.md](TECH_PRD.md) · [DECISIONS.md](DECISIONS.md) ·
[CLAUDE.md](CLAUDE.md)

---

## Start here: reading order for a new agent or developer

1. **[CLAUDE.md](CLAUDE.md)** — the working rules. Non-negotiable constraints
   (no vectors/embeddings, no `EXISTS { }`, secrets only in `.env`, synthetic
   data only, explain every change).
2. **This file** — current status and open items, so you don't redo finished
   work or trip on known issues.
3. **[README.md](README.md)** — the user-facing overview, setup, and the
   exact Cypher for all 12 queries.
4. **[ARCHITECTURE.md](ARCHITECTURE.md)** — components, flow, the full graph
   model, and what each tool walks and returns.
5. **[DECISIONS.md](DECISIONS.md)** — why things are the way they are. Check
   here before "improving" anything structural.
6. **[TECH_PRD.md](TECH_PRD.md)** — goals, non-goals and hackathon
   constraints.
7. Then the code, in dependency order: `graph.py` → `ingest.py` →
   `tools.py` → `agent.py`, with `company.json` alongside.

There is no `CONTEXT.md`. An early brief mentioned one, but it was never in the
project folder; everything it contained is covered by these docs.

## Status summary

| Area | Status |
|---|---|
| Graph model and dataset | ✅ Complete. 8 labels, 16 relationship types, 62 nodes, 139 relationships. Dates consistent. |
| Ingestion (`ingest.py`, `--update`) | ✅ Working on FalkorDB Cloud. |
| Five tools (`tools.py`) | ✅ All working against the live graph. |
| Agent (`agent.py`) | ✅ Working. Last full demo: 5/5 correct (see below). |
| README | ✅ Data model, 12 queries identical to code, Track 03 mapping, setup. |
| Deeper docs | ✅ This file, ARCHITECTURE, TECH_PRD, DECISIONS. |
| Git repository | ❌ **Not initialised.** No commits, no remote. |
| Demo video | ❌ Not recorded. |
| Hackathon submission | ❌ Not submitted. |

## Verified against the live database

All on the FalkorDB Cloud instance (FalkorDB 4.22), 2026-10-18:

- **Connection** with `FALKORDB_SSL=false`.
- **Clean ingest:** exact counts — Person 15, System 8, Decision 6, Document 9,
  Incident 5, Project 7, Ticket 7, Team 5; all 16 relationship counts as listed
  in [ARCHITECTURE.md](ARCHITECTURE.md#43-relationship-types). No index
  creation errors.
- **Idempotent re-load:** ingesting again *without* wiping leaves every count
  unchanged. `python ingest.py --update` run directly: counts unchanged.
- **Property update:** changing a ticket's status and re-loading updates it in
  place (62 nodes before and after); restored afterwards.
- **Cypher constructs:** `any()` with a list parameter ✅, `IN $ids` ✅,
  variable-length path with `length()` ✅, `UNION` ✅, bare pattern predicates
  ✅, `EXISTS { }` ❌, `exists(pattern)` ❌. Details:
  [ARCHITECTURE.md](ARCHITECTURE.md#7-falkordb-facts-this-design-relies-on).
- **All five tools**, called directly, return correct answers and paths,
  including `find_experts` with `limit=5.0` (float) and no-match cases.
- **README Cypher:** a script confirmed all 12 `cypher` blocks in README.md
  appear verbatim (whitespace-normalised) in `tools.py`.
- **Full agent demo:** `python agent.py --demo` answered 5/5 correctly in
  2 m 15 s on `gemini-3.8-flash`, with the right tool each time and a "How I
  know this:" section each time. A live Gemini 503 was retried successfully
  mid-run. *This run predates the verbatim-quoting prompt change (D-018).*
- **Verbatim path quoting:** verified on `gemini-3.7-flash` for one question
  ("Who owns payments-service?" — exact match).
- **Retry logic:** offline tests with a fake client: 429 with retry delay,
  give-up on a 300 s delay, no retry on 404, pacing gaps, failure isolation.

## Not yet verified / never tested

- **A full `--demo` run on `gemini-3.7-flash`** with the verbatim-quoting
  prompt, checking that all five paths are quoted exactly. Reserved for the
  demo-video recording run.
- **Local Docker setup** (`docker run ... falkordb/falkordb:latest`). Documented
  in the README but never run — the development machine has no Docker.
- **`FALKORDB_SSL=true`.** Hung on connect against our instance (no error);
  other instances may require it.
- **Interactive mode** (`python agent.py` with no arguments) against real
  Gemini. Single-question and `--demo` modes are tested.
- **Gemini passing `max_depth`** to `blast_radius` (always defaulted so far).
- **Non-Windows platforms.** Developed and run on Windows 11, Python 3.12.

## Environment

### FalkorDB

- Hosted on **FalkorDB Cloud** (free tier). Connection details are in `.env`
  (`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`);
  never copy them anywhere else.
- `FALKORDB_SSL=false`. Graph name `company_brain`.
- The graph is currently built and populated. Rebuild with `python ingest.py`;
  apply data changes with `python ingest.py --update`.
- Visual exploration: the instance's browser in the FalkorDB Cloud console
  (select `company_brain`).

### Gemini

- **Committed default model:** `gemini-3.8-flash`. `agent.py` (`MODEL`),
  `.env.example` and `README.md` all agree. Chosen for judges cloning the repo:
  it is the newest numbered Flash model (least likely to be retired for new
  keys, as 2.5 was) and the one with a full 5/5 demo run.
- **Local override for the 18 Oct recording:** the developer's `.env` sets
  `GEMINI_MODEL=gemini-3.7-flash`, because 3.8-flash's daily quota on this key
  is exhausted until ~05:30 IST 19 Oct. Delete that line from `.env` after
  recording. This is the only place the two differ.
- `gemini-2.5-flash` returns 404 for new API keys even though it is still
  listed by the models API — being listed does not mean usable.
- Text Flash models this key lists (2026-10-18): 3.8, 3.7, 3.6, 3.5,
  3-preview, flash-latest, plus lite variants. Only **3.8** and **3.7** have
  been run with this agent.
- **Free-tier limits** (from Gemini's 429 responses on 2026-10-18), counted
  **per model, per Google Cloud project**:
  - 5 requests per minute
  - **20 requests per day**
- **Quota state on 2026-10-18:** `gemini-3.8-flash` daily quota exhausted
  (resets around 05:30 IST on 2026-10-19). `gemini-3.7-flash` had at least 2 of
  20 used at last check. A full `--demo` uses about 11 requests.
- **How `agent.py` copes** (D-017): requests are spaced 13 s apart
  (`60 / GEMINI_REQUESTS_PER_MINUTE + 1`); 429 and 5xx responses are retried
  with Gemini's suggested delay or 10/20/40/80 s backoff, up to 4 times; a
  suggested wait over 90 s (the daily limit) gives up immediately; a failed
  question is reported and the run continues. A full demo takes ~2–3 minutes.
- **Workarounds when quota runs out:** switch `GEMINI_MODEL` to another
  available Flash model (each has its own quota; untested ones may behave
  differently), or create a new API key in a **new** Google Cloud project
  (fresh quota). Raise `GEMINI_REQUESTS_PER_MINUTE` only on a paid key.

### Python

- Python 3.12 on Windows 11; dependencies in `requirements.txt` (installed
  globally on the development machine, not in a venv).
- Console output is UTF-8; `agent.py` prints `→`.

### Checking health without spending Gemini quota

The tools never import the Gemini library, so these cost nothing:

```powershell
python -c "import sys, tools; print('Gemini loaded:', 'google.genai' in sys.modules)"   # expect False
python -c "import tools, json; print(json.dumps(tools.trace_decision('retry'), indent=2))"
python -c "import tools, json; print(json.dumps(tools.blast_radius('ledger-db'), indent=2))"
```

## Known issues

| Issue | Impact | Notes |
|---|---|---|
| DEC-002's ticket list is imprecise | `trace_decision` lists PAY-1042, PAY-1043 and GRW-0311 as well as PAY-1190 | Its decider worked on all three payments-service projects. Fix would be an `IMPLEMENTS` edge — **deliberately skipped** (D-010). |
| Topic matching is crude | "-ing"/"-ed" not stemmed; generic words (e.g. "service") over-match | Keyword matching by design (D-009). |
| `--update` never deletes | Records removed from `company.json` stay in the graph | Use a clean `python ingest.py` to drop them. Future work. |
| Failed-question message is verbose | `[!] Could not answer` prints Gemini's full error body | Cosmetic; could print only `exc.message`. |
| Gemini may abbreviate its own "How I know this:" | Observed once before D-018 (listed 8 of 12 edges) | The "graph traversals executed" block printed by `agent.py` is always complete. |
| `find_experts` incident responders group by role | A person with different roles across incidents would appear twice | Does not occur in the current data. |
| Unused properties | `Person.slack`, `Team.charter`, `System.type`, `Project.repo`/`year`, `Document.created_at`, `Incident.severity`, `Ticket.created_at` are stored but no tool reads them | Attributes, not structure; every node label and edge type *is* traversed (D-021). |
| No automated tests in the repo | Verification so far used throwaway scripts | Consider adding a small test script that calls the five tools. |

## Open items

### Required for the hackathon submission (deadline 2026-10-18, 11:59 PM IST)

1. ~~Align the model name across files~~ — **done**: all committed files say
   `gemini-3.8-flash`; `.env` overrides to 3.7 for tonight only (see
   [Gemini](#gemini)).
2. **Create the public GitHub repo.** `git init`; before the first commit,
   grep every file except `.env` for the FalkorDB password and the Gemini API
   key (values are in `.env`) and confirm no matches; confirm `.env` is
   ignored (`git status` must not list it); commit; push.
3. **Record the demo video** using one `python agent.py --demo` run (this is
   also the pending full verbatim-path check).
4. **Submit** on the WeMakeDevs site: repo URL, video, Track 03.

### Deliberately skipped (do not "fix" without asking)

- `(Ticket)-[:IMPLEMENTS]->(Decision)` edge (D-010).
- Chat ingestion (future work; stated in README).
- Frontend (D-007).

### Future work

See [TECH_PRD.md](TECH_PRD.md#73-future-work): chat ingestion, deletions on
re-ingest, live data sources, recency-weighted expertise, write actions.
