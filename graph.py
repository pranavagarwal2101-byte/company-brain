"""Shared FalkorDB connection helper."""

import os

from dotenv import load_dotenv
from falkordb import FalkorDB

# Loaded here, not only in agent.py, so ingest.py also picks up .env and so
# GRAPH_NAME below sees FALKORDB_GRAPH at import time.
load_dotenv()

GRAPH_NAME = os.getenv("FALKORDB_GRAPH", "company_brain")


def get_graph():
    """Return the FalkorDB graph handle used by every part of the project.

    Username and password are only needed for FalkorDB Cloud; a local Docker
    instance has no auth, and None is what the client expects then.
    """
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
        ssl=os.getenv("FALKORDB_SSL", "false").lower() == "true",
    )
    return db.select_graph(GRAPH_NAME)
