# Company Brain — Overview

**An agent that answers questions about how an engineering organisation works
by walking a FalkorDB knowledge graph, and shows the path it walked as
evidence.** Built for Graph Hacks 2026, Track 03: Company Brain.

## The problem

The most useful questions in a company have answers spread across records
that were written separately: a decision, the incident that caused it, the
RFC that justified it, the ticket that implemented it. Document search finds
text that *sounds* related. It cannot follow the links between those records,
so it cannot rebuild the chain, and it cannot show how it reached an answer.

## How it works

1. Company knowledge (people, teams, systems, projects, documents, tickets,
   incidents, decisions) is stored as a **graph** in FalkorDB.
2. You ask a question. **Gemini picks one of five pre-written graph
   traversals**. It never writes database queries itself.
3. The traversal runs, and returns the answer **plus the exact path of
   connections it followed**. The agent quotes that path under "How I know
   this:".

There is no vector search and no document retrieval. Without the graph, the
product cannot answer anything.

## Use cases

| You want to know… | Example | Tool |
|---|---|---|
| Who formally owns a system | "Who owns payments-service?" | `find_owner` |
| Who *actually* knows it, inferred from their work | "Who should review a change to payments-service?" → Aman (107 commits), though Riya is the owner (48) | `find_experts` |
| Why something is the way it is | "Why is the retry limit three?" → decision DEC-001, triggered by incident INC-212, justified by RFC-47, replaced the old limit of five, implemented in ticket PAY-1042 | `trace_decision` |
| What breaks if a system fails | "What breaks if ledger-db goes down?" → payments-service and audit-log directly; notification-service and api-gateway two hops away | `blast_radius` |
| Who to ask about a broad topic | "Who should I ask about audit events?" → Leila (owns it, wrote the ADR), then Victor and Grace | `who_to_ask` |

## Where to go next

- **Run it:** [README.md](README.md#setup). Two commands once `.env` is set.
- **See a real run:** [DEMO.md](DEMO.md)
- **How it's built:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Why it's built this way:** [DECISIONS.md](DECISIONS.md)
- **Current status:** [STATE.md](STATE.md)

## Glossary

| Term | Meaning |
|---|---|
| **Graph database** | A database that stores things (nodes) and the connections between them (edges) as first-class data, so following connections is fast and natural. FalkorDB is one. |
| **Node** | A thing in the graph: a person, a system, a decision. |
| **Label** | A node's type, e.g. `Person` or `System`. |
| **Edge / relationship** | A typed, directed connection between two nodes, e.g. `(Riya)-[:OWNS]->(payments-service)`. |
| **Property** | A detail stored on a node or edge, e.g. a person's email, or `commits` on a `WORKED_ON` edge. |
| **Cypher** | The query language for graph databases. A query describes a pattern of nodes and edges to find. |
| **Traversal** | Following edges from node to node to answer a question. |
| **Hop** | One edge crossed during a traversal. "Person → project → system" is two hops. |
| **Variable-length path** | A pattern that follows the same edge type a varying number of times, e.g. `-[:DEPENDS_ON*1..4]->` (1 to 4 hops). |
| **MERGE** | A Cypher command meaning "find this, and create it only if it isn't there". |
| **Idempotent** | Safe to repeat: running it again gives the same result instead of duplicating. MERGE makes ingestion idempotent. |
| **Parameter** | A `$value` in a query, sent separately and treated strictly as data. This prevents injection. |
| **Load-bearing** | The graph does work nothing else could. The opposite of decoration. |
| **Provenance** | Where a fact or decision came from: the incident, documents and people behind it. |
| **Inferred expertise** | Expertise worked out from what people did (commits, incidents), not from what anyone wrote down. |
| **RAG / vector search** | Retrieving text passages by similarity of meaning. Deliberately *not* used here. |
