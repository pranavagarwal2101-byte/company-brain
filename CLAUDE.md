# Working rules

## Required reading at session start
Before doing anything else in a new session, read these in order:
1. [STATE.md](STATE.md) -- current status, what is verified, known issues,
   open items. Start here.
2. [ARCHITECTURE.md](ARCHITECTURE.md) -- components, flow, graph model, tools.
3. [DECISIONS.md](DECISIONS.md) -- why things are the way they are. Check it
   before proposing structural changes; append a new entry for any new
   significant decision.
4. [TECH_PRD.md](TECH_PRD.md) -- goals, non-goals, hackathon constraints.
[README.md](README.md) stays the user-facing entry point. When status,
architecture or decisions change, update the matching doc in the same piece of
work -- especially STATE.md.

## Explain everything
- After every change, explain in plain English what you changed and why, at a
  level I could repeat to a judge. Do not just show a diff.
- When you write or modify a Cypher query, walk me through it clause by
  clause: what it matches, what it traverses, what it returns.
- If you make a design decision where another option was reasonable, say what
  you chose and why.
- Flag anything you are uncertain about rather than guessing. I would rather
  hear "this may not work on FalkorDB" than find out during the demo.

## Project constraints
- This is a Graph Hacks 2026 submission, Track 03: Company Brain. FalkorDB
  must be the primary graph database and must support a central part of the
  product.
- Never add a vector store, embeddings, or a document retriever. Every agent
  tool must remain a graph traversal. The hackathon disqualifies projects
  where the graph is decoration: "if the product still works once FalkorDB is
  taken out, the graph is decoration."
- Every ingested node and edge type should be traversed by at least one tool.
  Unused data looks decorative to a judge.
- Every tool returns both an answer and the traversal path that produced it.
  Explainability is a core feature, not an extra.

## Cypher
- UNION is supported on FalkorDB 4.22 (confirmed on the live instance) and
  may be used.
- EXISTS { MATCH ... } is NOT supported on FalkorDB 4.22 (parse error on the
  live instance). Never use it. Use the plain pattern predicate instead:
  WHERE (a)-[:R]->(b), or WHERE NOT (a)-[:R]->(b).
- Prefer splitting a complex query into simpler queries merged in Python over
  making one query cleverer. Clarity beats elegance here -- I have to explain
  it.
- Sanitise any value interpolated into a query string with int() or similar.

## Secrets
- Real credentials go in .env only, never in .env.example, README.md,
  CLAUDE.md or any committed file.
- Before any git commit, grep the repo for the FalkorDB password and the
  Gemini API key and confirm they appear nowhere but .env.

## Data
- company.json is synthetic. Keep it that way. Never introduce real company,
  personal or proprietary data.


