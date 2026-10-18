# Build Log

How Company Brain was built, in the order it happened — including what went
wrong. Written for Pranav to re-read, not for judges. "You" is Pranav; "I" is
Claude, the AI coding assistant.

Every technical term is explained the first time it appears. If you only want
the definitions, the glossary at the end of [OVERVIEW.md](OVERVIEW.md) has the
short versions.

---

## Stage 0 — The scaffold, written before any database existed

### What we were trying to do

Build an agent for Graph Hacks 2026, Track 03 ("Company Brain"): something
you can ask "why do we do it this way?" or "who knows this system?" and get a
grounded answer.

The core idea was to store company knowledge in a **graph database** instead
of a pile of documents. A graph database stores two kinds of things:

- **Nodes** — the things: a person, a system, a document, a decision. Each
  node has a **label** saying what kind of thing it is (`Person`, `System`)
  and **properties** holding its details (a person's name and email).
- **Edges** (also called **relationships**) — the connections between things,
  each with a type and a direction: `(Riya)-[:OWNS]->(payments-service)` means
  "Riya owns payments-service".

You ask a graph database questions in a query language called **Cypher**. A
Cypher query describes a *pattern* of nodes and edges to find, like
`MATCH (p:Person)-[:OWNS]->(s:System)` — "find every person who owns a
system".

Following edges from node to node is called a **traversal**. Each edge you
cross is one **hop**. "Who owns payments-service?" is one hop. "Who worked on
a project that uses payments-service?" is two hops: person → project → system.

### What we actually did

An earlier session (me, with your direction) wrote the whole project in one
go:

- `company.json` — **synthetic** (made-up) data for a fictional company,
  "Acme": 15 people, 8 systems, 6 decisions, and so on. Made up on purpose:
  the hackathon forbids real private data.
- `ingest.py` — reads that file and builds the graph.
- `tools.py` — five functions, each running fixed Cypher queries. These are the
  agent's **tools**.
- `agent.py` — the **agent loop**: it sends your question to Gemini (Google's
  **LLM**, a large language model, the AI that writes text), Gemini picks a
  tool, the tool runs against the graph, and Gemini writes the answer from the
  result.

One design choice made here mattered a lot later: **Gemini never writes
Cypher.** It can only choose one of the five pre-written tools. And every tool
returns not just an answer but the **path** — the list of edges it actually
walked — so every answer shows its evidence.

### What went wrong

Nothing had ever run. The environment where it was written couldn't download
the FalkorDB database (Docker Hub was blocked), so every query was untested.
The code *compiled* and was checked against fake database rows, but no real
database had ever seen a single query.

### What to take away

Code that compiles is not code that works. Anything touching an external
system — a database, an API — is a guess until it runs against the real thing.
We wrote "untested" down explicitly, and that honesty is what made the next
stage effective.

---

## Stage 1 — The review that found real bugs

### What we were trying to do

Before running anything, you asked me to read every file and report what I
thought would break.

### What we actually did

I read the brief, README, data and all four Python files, and listed suspected
problems. You then had me fix them in a numbered order (Group 1), stopping
after each group so you could see the change.

### What went wrong — and how we found out

**1. "retry" did not match "retries", and the headline demo was silently
broken.** The decision-tracing tool searched for the user's topic as one whole
piece of text: `toLower(d.statement) CONTAINS toLower($topic)`. The decision
says "Settlement **retries** are capped at three". The word "retries" does
*not* contain the string "retry" (r-e-t-r-**i**-e-s vs r-e-t-r-**y**). So the
star demo question — "why is the retry limit three?" — would have returned
"no decision found". Worse, the tool's own description told Gemini to pass
`'retry'` as an example.

Nothing would have crashed. It would just have quietly answered "nothing
found" during the demo. I found it by reading the query and comparing it,
letter by letter, against the actual data.

*Fix:* split the topic into separate words, cut off common endings (so "retry"
and "retries" both become "retr"), and match a decision if **any** word
appears. Decisions matching more words rank first.

**2. LIMIT with a decimal number.** `find_experts` had `LIMIT $limit`. `LIMIT`
caps how many rows come back, and it only accepts whole numbers. Gemini
sometimes sends numbers as decimals (`5.0` instead of `5`). *Fix:* convert to a
whole number in Python with `int()` and put it straight into the query.

That leads to an important idea, **parameters**. A `$name` in a query is a
parameter: the value is sent separately and the database treats it strictly as
data. That's safe. Pasting a value directly into the query text is risky, because
a crafted value could change what the query does (this is called **injection**).
So whenever we paste a value into query text, it goes through `int()` first, which
guarantees it's just a number.

**3. A false claim about FalkorDB.** The README said "FalkorDB has no
`UNION`" (`UNION` combines the results of two queries). Nobody had checked.
It was a guess written as a fact — and the hackathon judges work at FalkorDB.
(Stage 5 proved it false.)

**Smaller ones:** a sort order that referred to a field in a way FalkorDB might
reject; the superseded decision was reported by its full sentence instead of
its ID (`DEC-000`); and a redundant `DISTINCT`.

### What to take away

- The worst bugs aren't crashes. "retry" vs "retries" would have produced a
  calm, confident "nothing found" on camera. Check your demo's exact words
  against your exact data.
- Never put a guess in writing as a fact, especially about the sponsor's own
  product.
- Fixing in small numbered groups, and reviewing each one, kept every change
  explainable.

---

## Stage 2 — Making unused data load-bearing

### What we were trying to do

The hackathon has a rule: *"if the product still works once FalkorDB is taken
out, the graph is decoration"* — and decoration gets you disqualified.
"**Load-bearing**" is the opposite: the graph is doing real work that nothing
else could.

### What we actually did

I noticed that `Ticket` nodes and three edge types (`REPORTED`, `PART_OF`,
`REFERENCES`) were loaded into the graph but **no tool ever read them**. You
pointed out that this is exactly what a judge would call decoration: data put
in the graph for show.

We extended `trace_decision` so that, besides the incident and the documents,
it also finds:

- **tickets** that carried the decision out (so "why is the retry limit
  three?" now also shows ticket PAY-1042, "Cap settlement retries at three");
- **documents that cite** the justifying RFC (the on-call runbook and the
  onboarding guide both cite RFC-47).

The tricky part: there's no edge from a decision to a ticket. I compared three
routes through the graph and picked "projects that use the decision's system
**and** that the person who made the decision worked on". It's precise for 5 of
the 6 decisions. For one (DEC-002) it also picks up some unrelated tickets,
because that person worked on every payments project.

### What went wrong

- The imprecision on DEC-002. The exact fix would be a new edge type,
  `IMPLEMENTS`, from ticket to decision. **You decided not to add it:** one more
  thing to explain to judges, for a small gain. That trade-off is written down in
  DECISIONS.md (D-010).
- While testing, I found a data error: decision DEC-005 was dated *three months
  before* the incident that supposedly triggered it. We moved the incident's
  date (not the decision's) so the story reads in order.

### What to take away

- In a graph project, data nobody queries is a liability, not a bonus. Either
  use it or delete it.
- "Good enough, and documented as such" is a legitimate engineering decision
  under a deadline.
- Synthetic data still needs to make sense. A judge who spots a decision
  dated before its own cause will stop trusting everything else.

---

## Stage 3 — Moving to FalkorDB Cloud

### What we were trying to do

Get a real database running so we could test everything.

### What we actually did

You asked me to start downloading FalkorDB with Docker in the background.
**Docker** is a tool that runs software in self-contained packages called
containers. The command failed at once: Docker wasn't installed, and neither was WSL
(Windows' Linux layer, which Docker needs on Windows). Installing them means
admin rights and probably a restart: too slow on deadline day.

We switched to **FalkorDB Cloud**, a free hosted database. That needed a username
and password, which the code didn't support, so I added them to `graph.py`.

### What went wrong

1. **I started the Docker download without checking that Docker existed.** A
   one-second check first would have been better.
2. **A hidden bug in configuration loading.** The project reads its settings
   (database address, API key) from a file called `.env`. `ingest.py` never
   loaded that file, and `agent.py` loaded it *after* the database module had
   already read its settings. With the old local setup the defaults happened
   to work, so nobody noticed. With Cloud credentials, they'd have been
   silently ignored. *Fix:* load `.env` in `graph.py`, the module everything
   imports first.
3. **The credentials went into the wrong file.** You put the real Cloud
   password and Gemini key into `.env.example`, the *template* file that is
   meant to be committed publicly, instead of `.env`, which is kept private. We
   moved them, reset the template to placeholders, and searched every file for
   the password to confirm it appeared only in `.env`.

### What to take away

- Check that a tool exists before depending on it.
- "Works with the defaults" can hide bugs that only appear when the settings
  change.
- `.env` is secret and never committed; `.env.example` is public and holds only
  placeholders. Whenever you're about to publish, search for your real secrets
  first. That's now a rule in CLAUDE.md.

---

## Stage 4 — First contact with a live database

### What we were trying to do

Run the code against a real FalkorDB for the first time, and settle the
open questions with facts.

### What we actually did

- **Connected.** A trivial query returned `1`. TLS (encryption on the
  connection) had to be **off** for this instance; turning it on made the
  connection hang.
- **Ran `ingest.py`.** Every count matched: 62 nodes, 139 edges.
- **Tested the risky queries one at a time**, each as a tiny standalone query:

| Question | Result | What it means |
|---|---|---|
| Does `any(term IN $terms WHERE …)` work? (check if any item in a list matches) | ✅ Yes | The retry fix from Stage 1 works for real. |
| Does `UNION` work? | ✅ Yes | The README claim was false. We deleted it. |
| Does `EXISTS { MATCH … }` work? (a "does this pattern exist?" check) | ❌ No — parse error | Must never be used. The simpler form `WHERE (a)-[:R]->(b)` does work. |
| Does the variable-length path in blast radius work? | ✅ Yes | "Follow `DEPENDS_ON` 1 to 4 hops" works. |

A **variable-length path** is a pattern like `-[:DEPENDS_ON*1..4]->`: follow
this edge type between 1 and 4 times. It's how we find "everything that breaks
if auth-service goes down", including systems that only depend on it
indirectly.

### What went wrong — and a mistake worth remembering

**The re-run test.** We wanted to prove that `ingest.py` is **idempotent**:
running it again gives the same result instead of duplicating everything. The
property comes from **MERGE**, a Cypher command that means "find this node,
and create it only if it isn't already there" (unlike `CREATE`, which always
makes a new one).

Your plan was to run `ingest.py` twice and compare the counts. But `ingest.py`
**deletes the whole graph first**. Running it twice would show identical counts
even if MERGE were broken, because the duplicates would be wiped each time. The
test couldn't fail, so it proved nothing. I pointed this out and ran the real
test instead: load the data a second time *on top of* the existing graph, with
no delete. Counts stayed identical. We later added `ingest.py --update` so a
judge can run that test too.

Two other things surfaced:
- FalkorDB's `sum()` returns a decimal (`107.0` commits), which looked odd on
  screen. Fixed by converting to a whole number in Python.
- The **cross-team expert** finding appeared in the live output. Riya *owns*
  payments-service, but Aman has 107 commits on projects using it, against
  Riya's 48. That became the project's best example.

### What to take away

- Turn every "might not work" into a one-line test against the real system.
  Four tiny queries settled what hours of reasoning couldn't.
- **A test that cannot fail proves nothing.** Before trusting a test, ask:
  "if the thing were broken, would this test notice?"
- Some of the best findings only show up when real data flows through.

---

## Stage 5 — Honesty and polish fixes (Group 3)

### What we were trying to do

Make every claim in the README and code comments true, now that we had facts.

### What we actually did

- Deleted the false UNION claim entirely.
- Made the README show **all 12 queries** the code runs, copied exactly, and
  had a script confirm they match the code character for character (ignoring
  spaces).
- Replaced "arbitrary depth" with the truth: "up to 4 hops, configurable".
- Made `who_to_ask` match individual words like `trace_decision` does, so
  "audit events" finds three people instead of one.
- Made `who_to_ask` show its path in the same edge notation as the other tools.
- Fixed a message that told Cloud users to open `localhost:3000`, which only
  exists with Docker.

### What went wrong

- My first edge-notation path for `who_to_ask` listed the same project twice
  per person (once per system it touches). It was accurate but cluttered. I saw it
  in the test output and merged them into one line.
- A test failed because PowerShell mangled quote marks inside a one-line Python
  command. Moving the test into a script file fixed it. That was a test-harness
  problem, not a code problem, and the difference matters.

### What to take away

Docs that disagree with the code are a bug. A small script that checks them
against each other is cheap insurance.

---

## Stage 6 — The Gemini problems

### What we were trying to do

Run the full demo end to end with Gemini: five questions, each answered with
evidence.

### What went wrong — three separate problems

**1. The model had been retired.** The code asked for `gemini-2.5-flash`.
Gemini replied with an error: *no longer available to new users*. Oddly, the
model still appears when you list available models; it just doesn't work for
new accounts. I listed the models this key could use and switched to
`gemini-3.8-flash`.

**2. The rate limit.** A **rate limit** is a cap on how many requests you may
send in a period. Gemini's free tier allows **5 requests per minute**. Each
question takes about 2 requests (pick a tool, then write the answer), so the
five-question demo sends ~11 in a burst. It crashed on question 4 with error
**429** (the HTTP code for "too many requests"), printing a long traceback.

**3. The daily quota.** A **quota** is a total allowance. Separately from the
per-minute limit, the free tier allows only **20 requests per day per model**.
I didn't know this. I designed the fix around the per-minute limit, then ran
enough test demos that `gemini-3.8-flash` hit 20 and was locked out until the
next morning, after the deadline. It was worked around by switching to
`gemini-3.7-flash`, which has its own separate quota.

### The three-layer fix (for problem 2)

1. **Pacing:** wait at least 13 seconds between requests (60 ÷ 5, plus one
   second of margin), so we never hit the limit at all.
2. **Retry with backoff:** if Gemini still says 429 (or 5xx, meaning
   "overloaded"), wait and try again: first the delay Gemini suggests, otherwise
   10, then 20, 40, 80 seconds. **Backoff** means each retry waits longer than
   the last. If Gemini asks for a very long wait (over 90 seconds), that means
   the *daily* quota is gone, so it gives up immediately instead of hanging.
3. **Isolation:** if one question still fails, print a short message and move
   on to the next question instead of crashing the whole run.

It worked. The next full demo answered **5/5 in 2 minutes 15 seconds**, and
along the way survived a real "overloaded" error from Gemini, which it retried
automatically. That run is preserved in [DEMO.md](DEMO.md).

### One more fix: quote, don't describe

In that run, Gemini rewrote one path in its own style instead of copying it.
You spotted why that matters: the project's claim is that the agent *cites*
the traversal it walked. If it rewords the path, it's *describing* the
traversal instead. We added a rule to Gemini's instructions: copy each path
exactly, character for character. Tested on one question with
`gemini-3.7-flash`: exact match.

### What went wrong on my side

- I didn't check the daily quota before spending requests on repeated full
  demo runs. Free-tier limits come in **two** sizes, per-minute and per-day, and
  I only planned for one. The full five-question check of exact quoting is
  still waiting for the recording run because of this.
- The default model then changed three times in one evening (3.8 → 3.7 → back
  to 3.8). The final rule was clear and worth remembering: the default must
  suit a **judge cloning the repo tomorrow** with fresh quota, not whichever
  model has quota left for us tonight. Your own `.env` overrides it for
  tonight.

### What to take away

- External services fail in ways your code doesn't control: retired models,
  limits, overloads. Plan for failure, not just success.
- Read the limits page before you start spending a scarce resource.
- Every Gemini call costs quota; the graph tools cost nothing. When you just
  want to understand the project, call the tools directly
  (`python -c "import tools; ..."`). That's what the notification-backlog
  walkthrough did, at zero quota.

---

## Stage 7 — The documentation pass

### What we were trying to do

Make the project understandable without you in the room: for judges, for a
future AI session, or for you in a month.

### What we actually did

- **CLAUDE.md** — standing rules for AI assistants: explain every change, no
  vector search, never use `EXISTS { }`, secrets only in `.env`, synthetic
  data only.
- **ARCHITECTURE.md** — how it all fits together, with diagrams.
- **TECH_PRD.md** — the problem, goals, non-goals, hackathon rules.
- **DECISIONS.md** — 21 design decisions, each with the alternatives rejected.
- **STATE.md** — what works, what's verified, what's untested, what's open.
- **README** — a table of contents, Setup moved before the reference material,
  and the old text-art diagram replaced.

The diagrams are written in **Mermaid**, a text format that GitHub turns into
pictures. Because they're text, a future agent can read and edit them.

### What went wrong

- **CLAUDE.md was out of date almost immediately.** It said "don't use UNION or
  EXISTS until tested". By then we had tested both, and the rule was rewritten
  with the actual results.
- **I wrote a wrong number.** ARCHITECTURE.md first said 136 relationships. A
  live count said 139, and I fixed it. Counting by hand is how wrong numbers get
  into docs.
- **Nobody had ever seen the diagrams drawn.** You insisted on rendering every
  one before pushing. I installed a local renderer (mermaid-cli, using your
  Chrome). The first schema diagram, as you'd predicted, rendered as a tangle of
  crossing lines. I compared three layouts and picked the top-to-bottom grouped
  one. Rendering a whole file at once kept timing out, so I rendered each
  diagram on its own: 22 of 22 passed, in light and dark themes.
- **You asked for work that was already done**, twice: re-running validation
  that had just passed, and replacing the README diagram after it had been
  replaced. Easy to do at the end of a long day, and exactly the problem
  STATE.md now exists to prevent.

### What to take away

- Documentation drifts the moment the code changes. Keep one "current state"
  file (STATE.md) and update it as part of the work, not afterwards.
- Verify docs the same way you verify code: count with a query, render the
  diagrams, check that the links resolve.

---

## Where it ended up

Everything in the product works and has been checked against the live
database. What's left is not engineering: the public repository, the demo
video and the submission form. The current list is in
[STATE.md](STATE.md#open-items).

## The lessons, in one list

1. Untested code is a hypothesis. Run it against the real system early.
2. Quiet failures ("nothing found") are worse than crashes. Test your exact
   demo wording.
3. Turn every "might not work" into a tiny, separate test.
4. A test that can't fail proves nothing.
5. Never state a guess as a fact, least of all about the sponsor's product.
6. Unused data in a graph looks like decoration. Use it or remove it.
7. Secrets go in `.env` only. Search for them before publishing.
8. External APIs have limits in more than one dimension. Read them first.
9. Plan for failure: pace, retry, isolate.
10. Keep docs true by checking them mechanically, and keep one file that says
    where things stand.
