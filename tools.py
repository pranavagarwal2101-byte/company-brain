"""Graph-backed tools the agent can call.

Every tool returns a dict with two keys:

    answer : the data the agent should use to reply
    path   : the traversal that produced it, in human readable form

The `path` is what makes this explainable. The agent is instructed to show it,
so every answer carries the chain of relationships it came from rather than a
bare assertion.
"""

import re

from graph import get_graph

_graph = None


def g():
    """Lazily open one shared graph connection."""
    global _graph
    if _graph is None:
        _graph = get_graph()
    return _graph


def _rows(cypher, params=None):
    return g().query(cypher, params or {}).result_set


# ---------------------------------------------------------------------------
# 1. Ownership — a single hop, the simplest case
# ---------------------------------------------------------------------------

def find_owner(system: str) -> dict:
    """Who formally owns a system, and which team they sit on."""
    rows = _rows(
        """
        MATCH (p:Person)-[:OWNS]->(s:System)
        WHERE s.name = $system
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.name AS name, p.email AS email, p.role AS role,
               t.name AS team, s.name AS system, s.tier AS tier
        """,
        {"system": system},
    )
    if not rows:
        return {
            "answer": f"No owner recorded for '{system}'.",
            "path": f"(:Person)-[:OWNS]->(:System {{name:'{system}'}})  — no match",
        }

    owners = [
        {"name": r[0], "email": r[1], "role": r[2], "team": r[3], "tier": r[5]}
        for r in rows
    ]
    return {
        "answer": {"system": system, "owners": owners},
        "path": " | ".join(
            f"(Person:{o['name']})-[:OWNS]->(System:{system}); "
            f"(Person:{o['name']})-[:MEMBER_OF]->(Team:{o['team']})"
            for o in owners
        ),
    }


# ---------------------------------------------------------------------------
# 2. Expertise — two hops, and the answer exists in no single record
# ---------------------------------------------------------------------------

def find_experts(system: str, limit: int = 5) -> dict:
    """Who has hands-on experience with a system.

    Expertise is never stated anywhere. It is derived by walking
    Person -> Project -> System and weighing commits, then adding anyone who
    responded to an incident on that system. This is the query that cannot be
    answered by retrieving a document.
    """
    # LIMIT is inlined as an int rather than passed as $limit: Gemini can send
    # numbers as floats (5.0), and LIMIT only accepts an integer.
    rows = _rows(
        f"""
        MATCH (p:Person)-[w:WORKED_ON]->(pr:Project)-[:USES]->(s:System)
        WHERE s.name = $system
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.name AS name, p.email AS email, t.name AS team,
               sum(w.commits) AS commits,
               collect(DISTINCT pr.name) AS projects
        ORDER BY commits DESC
        LIMIT {max(1, int(limit))}
        """,
        {"system": system},
    )

    incident_rows = _rows(
        """
        MATCH (p:Person)-[r:PARTICIPATED_IN]->(i:Incident)-[:AFFECTED]->(s:System)
        WHERE s.name = $system
        RETURN p.name AS name, collect(DISTINCT i.id) AS incidents,
               r.role AS role
        """,
        {"system": system},
    )

    experts = [
        {
            "name": r[0],
            "email": r[1],
            "team": r[2],
            # FalkorDB's sum() returns a float (107.0); commits are whole numbers.
            "commits_on_related_projects": int(r[3]),
            "via_projects": r[4],
        }
        for r in rows
    ]
    responders = [{"name": r[0], "incidents": r[1], "role": r[2]} for r in incident_rows]

    if not experts and not responders:
        return {
            "answer": f"No one found with experience on '{system}'.",
            "path": f"(:Person)-[:WORKED_ON]->(:Project)-[:USES]->(:System {{name:'{system}'}})  — no match",
        }

    path_parts = [
        f"(Person:{e['name']})-[:WORKED_ON]->(Project:{'/'.join(e['via_projects'])})"
        f"-[:USES]->(System:{system})  [{e['commits_on_related_projects']} commits]"
        for e in experts
    ]
    path_parts += [
        f"(Person:{r['name']})-[:PARTICIPATED_IN]->(Incident:{'/'.join(r['incidents'])})"
        f"-[:AFFECTED]->(System:{system})"
        for r in responders
    ]

    return {
        "answer": {
            "system": system,
            "by_contribution": experts,
            "incident_responders": responders,
        },
        "path": " | ".join(path_parts),
    }


# ---------------------------------------------------------------------------
# 3. Decision provenance — the "why do we do it this way" chain
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "are", "was", "why", "what", "how", "who", "does",
    "did", "our", "this", "that", "with", "about", "from", "into", "its",
}


def _stem(word: str) -> str:
    """Crude suffix strip so 'retry' and 'retries' both become 'retr'."""
    for suffix in ("ies", "es", "s", "y"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _search_terms(topic: str) -> list:
    """Turn a free-text topic into lowercase stems to match with CONTAINS.

    'settlement retry limit' -> ['settlement', 'retr', 'limit']
    Hyphenated names stay whole, so 'payments-service' is one term.
    """
    words = re.findall(r"[a-z0-9][a-z0-9-]*", topic.lower())
    terms = [_stem(w) for w in words if len(w) >= 3 and w not in _STOPWORDS]
    return terms or [topic.lower()]


def trace_decision(topic: str) -> dict:
    """Trace a decision back to the incident that caused it and the docs
    that justify it, including any decision it replaced. Also returns the
    tickets that carried the decision out and the documents that cite its
    justification."""
    # The topic is split into word stems, and a decision matches if ANY stem
    # appears in its statement or its system's name. Decisions that match more
    # stems are ranked first (in Python, below).
    terms = _search_terms(topic)
    rows = _rows(
        """
        MATCH (d:Decision)-[:ABOUT]->(sys:System)
        WHERE any(term IN $terms WHERE toLower(d.statement) CONTAINS term
                                    OR toLower(sys.name) CONTAINS term)
        OPTIONAL MATCH (d)-[:TRIGGERED_BY]->(i:Incident)
        OPTIONAL MATCH (d)-[:SUPERSEDES]->(old:Decision)
        OPTIONAL MATCH (owner:Person)-[:DECIDED]->(d)
        RETURN d.id AS id, d.statement AS statement, d.status AS status,
               d.made_at AS made_at, sys.name AS system,
               i.id AS incident_id, i.title AS incident_title,
               i.occurred_at AS incident_date, i.summary AS incident_summary,
               old.id AS superseded_id, old.statement AS superseded_statement,
               old.made_at AS superseded_at,
               owner.name AS decided_by
        ORDER BY made_at DESC
        """,
        {"terms": terms},
    )

    # Justifying documents fetched separately, then attached by decision id.
    doc_rows = _rows(
        """
        MATCH (d:Decision)-[:JUSTIFIED_BY]->(doc:Document)
        RETURN d.id AS id, doc.id AS doc_id, doc.title AS title, doc.url AS url
        """
    )
    docs_by_decision = {}
    for dec_id, doc_id, title, url in doc_rows:
        docs_by_decision.setdefault(dec_id, []).append(
            {"id": doc_id, "title": title, "url": url}
        )

    if not rows:
        return {
            "answer": f"No decision found matching '{topic}'.",
            "path": f"(:Decision) WHERE statement/system CONTAINS any of {terms}  — no match",
        }

    def score(row):
        """How many search terms this decision matched."""
        text = f"{row[1]} {row[4]}".lower()
        return sum(1 for term in terms if term in text)

    # sorted() is stable, so equal scores keep the newest-first order from Cypher.
    rows = sorted(rows, key=lambda row: -score(row))
    ids = [r[0] for r in rows]

    # Tickets that carried the decision out. There is no Decision->Project
    # edge, so we take projects that use the decision's system AND that the
    # person who made the decision worked on, then the tickets on those
    # projects. Active decisions only: follow-up work on a superseded decision
    # belongs to the decision that replaced it.
    ticket_rows = _rows(
        """
        MATCH (decider:Person)-[:DECIDED]->(d:Decision)-[:ABOUT]->(:System)<-[:USES]-(pr:Project)
        WHERE d.id IN $ids AND d.status = 'active'
        MATCH (decider)-[:WORKED_ON]->(pr)
        MATCH (t:Ticket)-[:PART_OF]->(pr)
        OPTIONAL MATCH (rep:Person)-[:REPORTED]->(t)
        RETURN d.id AS id, pr.name AS project, t.id AS ticket_id,
               t.title AS title, t.status AS status, rep.name AS reported_by
        ORDER BY ticket_id
        """,
        {"ids": ids},
    )
    tickets_by_decision = {}
    for dec_id, project, ticket_id, title, status, reported_by in ticket_rows:
        tickets_by_decision.setdefault(dec_id, []).append(
            {"id": ticket_id, "title": title, "status": status,
             "project": project, "reported_by": reported_by}
        )

    # Documents that cite a justifying document, e.g. the runbook citing RFC-47.
    cite_rows = _rows(
        """
        MATCH (d:Decision)-[:JUSTIFIED_BY]->(j:Document)<-[:REFERENCES]-(citing:Document)
        WHERE d.id IN $ids
        RETURN d.id AS id, citing.id AS doc_id, citing.title AS title,
               citing.type AS type, j.id AS cites
        ORDER BY doc_id
        """,
        {"ids": ids},
    )
    citing_by_decision = {}
    for dec_id, doc_id, title, doc_type, cites in cite_rows:
        citing_by_decision.setdefault(dec_id, []).append(
            {"id": doc_id, "title": title, "type": doc_type, "cites": cites}
        )

    results, path_parts = [], []
    for r in rows:
        (dec_id, statement, status, made_at, system,
         inc_id, inc_title, inc_date, inc_summary,
         old_id, old_statement, old_made_at, decided_by) = r

        docs = docs_by_decision.get(dec_id, [])
        tickets = tickets_by_decision.get(dec_id, [])
        # A justifying doc that cites another justifying doc is not new evidence.
        justified_ids = {d["id"] for d in docs}
        cited_by = [
            c for c in citing_by_decision.get(dec_id, [])
            if c["id"] not in justified_ids
        ]
        entry = {
            "decision_id": dec_id,
            "statement": statement,
            "status": status,
            "made_at": made_at,
            "about_system": system,
            "decided_by": decided_by,
            "triggered_by": (
                {
                    "id": inc_id,
                    "title": inc_title,
                    "occurred_at": inc_date,
                    "summary": inc_summary,
                }
                if inc_id
                else None
            ),
            "justified_by": docs,
            "cited_by": cited_by,
            "tickets": tickets,
            "supersedes": (
                {"id": old_id, "statement": old_statement, "made_at": old_made_at}
                if old_id
                else None
            ),
        }
        results.append(entry)

        chain = f"(Decision:{dec_id})-[:ABOUT]->(System:{system})"
        if decided_by:
            chain += f"; (Person:{decided_by})-[:DECIDED]->(Decision:{dec_id})"
        if inc_id:
            chain += f"; (Decision:{dec_id})-[:TRIGGERED_BY]->(Incident:{inc_id})"
        for d in docs:
            chain += f"; (Decision:{dec_id})-[:JUSTIFIED_BY]->(Document:{d['id']})"
        for c in cited_by:
            chain += f"; (Document:{c['id']})-[:REFERENCES]->(Document:{c['cites']})"
        for project in dict.fromkeys(t["project"] for t in tickets):
            chain += (f"; (Person:{decided_by})-[:WORKED_ON]->(Project:{project})"
                      f"-[:USES]->(System:{system})")
        for t in tickets:
            chain += (f"; (Person:{t['reported_by']})-[:REPORTED]->(Ticket:{t['id']})"
                      f"-[:PART_OF]->(Project:{t['project']})")
        if old_id:
            chain += f"; (Decision:{dec_id})-[:SUPERSEDES]->(Decision:{old_id})"
        path_parts.append(chain)

    return {"answer": {"topic": topic, "decisions": results}, "path": " | ".join(path_parts)}


# ---------------------------------------------------------------------------
# 4. Blast radius — transitive traversal, up to 4 hops (configurable)
# ---------------------------------------------------------------------------

def blast_radius(system: str, max_depth: int = 4) -> dict:
    """What breaks if this system goes down.

    Follows DEPENDS_ON edges backwards transitively: anything that depends on
    the system, and anything that depends on those, up to max_depth hops
    (default 4, configurable). A fixed schema join cannot express this; a
    variable-length traversal can.
    """
    rows = _rows(
        f"""
        MATCH path = (affected:System)-[:DEPENDS_ON*1..{int(max_depth)}]->(s:System)
        WHERE s.name = $system
        OPTIONAL MATCH (p:Person)-[:OWNS]->(affected)
        RETURN affected.name AS name, affected.tier AS tier,
               min(length(path)) AS hops,
               collect(DISTINCT p.name) AS owners
        ORDER BY hops, name
        """,
        {"system": system},
    )

    direct = _rows(
        """
        MATCH (s:System)-[:DEPENDS_ON]->(dep:System)
        WHERE s.name = $system
        RETURN collect(dep.name) AS depends_on
        """,
        {"system": system},
    )
    upstream = direct[0][0] if direct else []

    if not rows:
        return {
            "answer": {
                "system": system,
                "impacted": [],
                "this_system_depends_on": upstream,
                "note": "Nothing depends on this system.",
            },
            "path": f"(:System)-[:DEPENDS_ON*1..{max_depth}]->(System:{system})  — no match",
        }

    impacted = [
        {"system": r[0], "tier": r[1], "hops_away": r[2], "owners": r[3]}
        for r in rows
    ]
    return {
        "answer": {
            "system": system,
            "impacted": impacted,
            "this_system_depends_on": upstream,
        },
        "path": " | ".join(
            f"(System:{i['system']})-[:DEPENDS_ON*{i['hops_away']}]->(System:{system})"
            for i in impacted
        ),
    }


# ---------------------------------------------------------------------------
# 5. Who to ask — combines ownership, authorship and project contributions
# ---------------------------------------------------------------------------

def who_to_ask(topic: str) -> dict:
    """Find the right person for a topic, ranked by how they connect to it.

    Looks across three relationship types -- OWNS, AUTHORED and WORKED_ON --
    which is exactly the sort of question that has no single source document.
    The topic is split into word stems the same way as trace_decision, so
    'audit events' matches on 'audit' or 'event'.
    """
    # Three separate traversals, one per edge type, merged and ranked in Python.
    terms = _search_terms(topic)
    owner_rows = _rows(
        """
        MATCH (p:Person)-[:OWNS]->(s:System)
        WHERE any(term IN $terms WHERE toLower(s.name) CONTAINS term)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.name, p.email, t.name, s.name
        """,
        {"terms": terms},
    )
    author_rows = _rows(
        """
        MATCH (p:Person)-[:AUTHORED]->(d:Document)
        WHERE any(term IN $terms WHERE toLower(d.title) CONTAINS term
                                    OR toLower(d.body) CONTAINS term)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.name, p.email, t.name, d.id, d.title
        """,
        {"terms": terms},
    )
    worked_rows = _rows(
        """
        MATCH (p:Person)-[:WORKED_ON]->(pr:Project)-[:USES]->(s:System)
        WHERE any(term IN $terms WHERE toLower(s.name) CONTAINS term
                                    OR toLower(pr.name) CONTAINS term)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.name, p.email, t.name, pr.name, s.name
        """,
        {"terms": terms},
    )

    if not (owner_rows or author_rows or worked_rows):
        return {
            "answer": f"No one found connected to '{topic}'.",
            "path": f"OWNS / AUTHORED / WORKED_ON edges matching any of {terms}  — no match",
        }

    # rank 1 = owns (strongest signal), 2 = wrote the doc, 3 = worked on it.
    # Each hit carries a readable reason for the answer and the edge it came
    # from for the path.
    collected = []
    for name, email, team, sys_name in owner_rows:
        collected.append((name, email, team, 1, f"owns {sys_name}",
                          f"(Person:{name})-[:OWNS]->(System:{sys_name})"))
    for name, email, team, doc_id, title in author_rows:
        collected.append((name, email, team, 2, f"wrote {doc_id} ({title})",
                          f"(Person:{name})-[:AUTHORED]->(Document:{doc_id})"))
    # A project that uses several systems comes back once per system; fold
    # those rows into one edge per project, like find_experts does.
    worked_systems = {}
    for name, email, team, proj, sys_name in worked_rows:
        worked_systems.setdefault((name, email, team, proj), set()).add(sys_name)
    for (name, email, team, proj), systems in worked_systems.items():
        collected.append((name, email, team, 3, f"worked on {proj}",
                          f"(Person:{name})-[:WORKED_ON]->(Project:{proj})"
                          f"-[:USES]->(System:{'/'.join(sorted(systems))})"))

    people, edges = {}, {}
    for name, email, team, rank, reason, edge in collected:
        entry = people.setdefault(
            email, {"name": name, "email": email, "team": team, "reasons": [], "rank": rank}
        )
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)
        entry["rank"] = min(entry["rank"], rank)
        person_edges = edges.setdefault(email, [])
        if edge not in person_edges:
            person_edges.append(edge)

    ranked = sorted(people.values(), key=lambda p: (p["rank"], -len(p["reasons"])))
    return {
        "answer": {"topic": topic, "people": ranked},
        "path": " | ".join("; ".join(edges[p["email"]]) for p in ranked),
    }


# ---------------------------------------------------------------------------
# Registry used by the agent
# ---------------------------------------------------------------------------

TOOLS = {
    "find_owner": find_owner,
    "find_experts": find_experts,
    "trace_decision": trace_decision,
    "blast_radius": blast_radius,
    "who_to_ask": who_to_ask,
}
