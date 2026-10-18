"""Load the synthetic company dataset into FalkorDB as a knowledge graph.

    python ingest.py            clean build: wipe the graph, then load
    python ingest.py --update   load on top of the existing graph, no wipe

Every write is a MERGE, so --update adds new records and refreshes changed
properties without duplicating anything already in the graph.
"""

import json
import os
import sys

from graph import GRAPH_NAME, get_graph


def load_data(path="company.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def wipe(graph):
    """Drop the graph so re-running ingest is always a clean build."""
    try:
        graph.delete()
    except Exception:
        # Graph did not exist yet, which is fine on a first run.
        pass


def create_indexes(graph):
    """Indexes on the identifiers every traversal starts from."""
    statements = [
        "CREATE INDEX FOR (p:Person) ON (p.email)",
        "CREATE INDEX FOR (s:System) ON (s.name)",
        "CREATE INDEX FOR (d:Document) ON (d.id)",
        "CREATE INDEX FOR (dec:Decision) ON (dec.id)",
        "CREATE INDEX FOR (i:Incident) ON (i.id)",
        "CREATE INDEX FOR (pr:Project) ON (pr.name)",
        "CREATE INDEX FOR (t:Ticket) ON (t.id)",
        "CREATE INDEX FOR (tm:Team) ON (tm.name)",
    ]
    for stmt in statements:
        try:
            graph.query(stmt)
        except Exception as exc:  # index may already exist
            print(f"  index skipped: {exc}")


def ingest(graph, data):
    # --- Teams -----------------------------------------------------------
    for team in data["teams"]:
        graph.query(
            "MERGE (t:Team {name: $name}) SET t.charter = $charter",
            {"name": team["name"], "charter": team["charter"]},
        )

    # --- People and team membership --------------------------------------
    for person in data["people"]:
        graph.query(
            """
            MERGE (p:Person {email: $email})
            SET p.name = $name, p.role = $role, p.slack = $slack
            """,
            person,
        )
        graph.query(
            """
            MATCH (p:Person {email: $email}), (t:Team {name: $team})
            MERGE (p)-[:MEMBER_OF]->(t)
            """,
            person,
        )

    # --- Systems ---------------------------------------------------------
    for system in data["systems"]:
        graph.query(
            "MERGE (s:System {name: $name}) SET s.type = $type, s.tier = $tier",
            system,
        )

    # --- System dependency edges (powers blast radius) -------------------
    for dep in data["depends_on"]:
        graph.query(
            """
            MATCH (a:System {name: $from}), (b:System {name: $to})
            MERGE (a)-[:DEPENDS_ON]->(b)
            """,
            dep,
        )

    # --- Ownership -------------------------------------------------------
    for own in data["owns"]:
        graph.query(
            """
            MATCH (p:Person {email: $person}), (s:System {name: $system})
            MERGE (p)-[:OWNS]->(s)
            """,
            own,
        )

    # --- Projects --------------------------------------------------------
    for project in data["projects"]:
        graph.query(
            "MERGE (pr:Project {name: $name}) SET pr.repo = $repo, pr.year = $year",
            project,
        )

    for link in data["project_uses"]:
        graph.query(
            """
            MATCH (pr:Project {name: $project}), (s:System {name: $system})
            MERGE (pr)-[:USES]->(s)
            """,
            link,
        )

    # --- Who worked on what (powers expertise, which is inferred) --------
    for work in data["worked_on"]:
        graph.query(
            """
            MATCH (p:Person {email: $person}), (pr:Project {name: $project})
            MERGE (p)-[w:WORKED_ON]->(pr)
            SET w.commits = $commits
            """,
            work,
        )

    # --- Incidents -------------------------------------------------------
    for inc in data["incidents"]:
        graph.query(
            """
            MERGE (i:Incident {id: $id})
            SET i.title = $title, i.occurred_at = $occurred_at,
                i.severity = $severity, i.summary = $summary
            """,
            inc,
        )

    for link in data["incident_affects"]:
        graph.query(
            """
            MATCH (i:Incident {id: $incident}), (s:System {name: $system})
            MERGE (i)-[:AFFECTED]->(s)
            """,
            link,
        )

    for link in data["incident_participants"]:
        graph.query(
            """
            MATCH (p:Person {email: $person}), (i:Incident {id: $incident})
            MERGE (p)-[r:PARTICIPATED_IN]->(i)
            SET r.role = $role
            """,
            link,
        )

    # --- Documents -------------------------------------------------------
    for doc in data["documents"]:
        graph.query(
            """
            MERGE (d:Document {id: $id})
            SET d.title = $title, d.type = $type, d.url = $url,
                d.created_at = $created_at, d.body = $body
            """,
            doc,
        )
        graph.query(
            """
            MATCH (p:Person {email: $author}), (d:Document {id: $id})
            MERGE (p)-[:AUTHORED]->(d)
            """,
            doc,
        )

    for ref in data["doc_references"]:
        graph.query(
            """
            MATCH (a:Document {id: $from}), (b:Document {id: $to})
            MERGE (a)-[:REFERENCES]->(b)
            """,
            ref,
        )

    # --- Tickets ---------------------------------------------------------
    for ticket in data["tickets"]:
        graph.query(
            """
            MERGE (t:Ticket {id: $id})
            SET t.title = $title, t.status = $status, t.created_at = $created_at
            """,
            ticket,
        )
        graph.query(
            """
            MATCH (p:Person {email: $reporter}), (t:Ticket {id: $id})
            MERGE (p)-[:REPORTED]->(t)
            """,
            ticket,
        )
        graph.query(
            """
            MATCH (t:Ticket {id: $id}), (pr:Project {name: $project})
            MERGE (t)-[:PART_OF]->(pr)
            """,
            ticket,
        )

    # --- Decisions (the provenance spine) --------------------------------
    for dec in data["decisions"]:
        graph.query(
            """
            MERGE (d:Decision {id: $id})
            SET d.statement = $statement, d.made_at = $made_at, d.status = $status
            """,
            {
                "id": dec["id"],
                "statement": dec["statement"],
                "made_at": dec["made_at"],
                "status": dec["status"],
            },
        )

    for dec in data["decisions"]:
        graph.query(
            """
            MATCH (d:Decision {id: $id}), (s:System {name: $system})
            MERGE (d)-[:ABOUT]->(s)
            """,
            {"id": dec["id"], "system": dec["about_system"]},
        )

        graph.query(
            """
            MATCH (d:Decision {id: $id}), (p:Person {email: $person})
            MERGE (p)-[:DECIDED]->(d)
            """,
            {"id": dec["id"], "person": dec["decided_by"]},
        )

        if dec.get("triggered_by"):
            graph.query(
                """
                MATCH (d:Decision {id: $id}), (i:Incident {id: $incident})
                MERGE (d)-[:TRIGGERED_BY]->(i)
                """,
                {"id": dec["id"], "incident": dec["triggered_by"]},
            )

        for doc_id in dec.get("justified_by", []):
            graph.query(
                """
                MATCH (d:Decision {id: $id}), (doc:Document {id: $doc})
                MERGE (d)-[:JUSTIFIED_BY]->(doc)
                """,
                {"id": dec["id"], "doc": doc_id},
            )

        if dec.get("supersedes"):
            graph.query(
                """
                MATCH (new:Decision {id: $id}), (old:Decision {id: $old})
                MERGE (new)-[:SUPERSEDES]->(old)
                """,
                {"id": dec["id"], "old": dec["supersedes"]},
            )


def summarise(graph):
    rows = graph.query(
        """
        MATCH (n)
        RETURN labels(n)[0] AS label, count(*) AS count
        ORDER BY label
        """
    ).result_set
    print("\nNodes created:")
    for label, count in rows:
        print(f"  {label:<10} {count}")

    rows = graph.query(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS rel, count(*) AS count
        ORDER BY rel
        """
    ).result_set
    print("\nRelationships created:")
    for rel, count in rows:
        print(f"  {rel:<18} {count}")


def main():
    update = "--update" in sys.argv[1:]
    data = load_data()
    graph = get_graph()

    if update:
        # No wipe: MERGE matches existing nodes and edges by key and updates
        # them in place. Indexes already exist from the initial build.
        print(f"Updating graph '{GRAPH_NAME}' in place (no wipe)...")
        ingest(graph, data)
    else:
        print(f"Building graph '{GRAPH_NAME}'...")
        wipe(graph)
        ingest(graph, data)
        create_indexes(graph)
    summarise(graph)
    # The browser UI on port 3000 only exists for a local Docker instance.
    if os.getenv("FALKORDB_HOST", "localhost") in ("localhost", "127.0.0.1"):
        print("\nDone. Open http://localhost:3000 to explore the graph.")
    else:
        print("\nDone. Explore the graph from your FalkorDB Cloud console.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        print("Check FALKORDB_HOST / FALKORDB_PORT in .env, or start FalkorDB locally:")
        print("  docker run -d -p 6379:6379 -p 3000:3000 --name falkordb falkordb/falkordb:latest")
        sys.exit(1)
