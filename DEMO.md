# Demo Run

A real, unedited run of `python agent.py --demo`, captured during development.
No output has been changed. Long lines are as printed.

| | |
|---|---|
| **Date** | 2026-10-18 |
| **Command** | `python agent.py --demo` |
| **Model** | `gemini-3.8-flash` (free tier, paced to 5 requests/minute) |
| **Database** | FalkorDB Cloud, graph `company_brain` (62 nodes, 139 relationships) |
| **Result** | **5/5 questions answered in 2 m 15 s** |
| **Notable** | Gemini returned a 503 ("overloaded") on question 3; `agent.py` waited 10 s and retried automatically. |

**What to read in each answer.** The line starting `→` is the tool Gemini
chose. The answer ends with Gemini's "How I know this:" section. The block
`--- graph traversals executed ---` is printed by `agent.py` itself, straight
from the tool results, so it is always the exact path that ran.

**One honest caveat.** This run happened *before* the rule requiring Gemini
to quote paths verbatim ([DECISIONS.md](DECISIONS.md) D-018). In question 1,
Gemini rewrote the path in its own style (`(:Person {name: "Riya
Sharma"})…`) instead of copying it. The content is correct, and the exact path
is in the "graph traversals executed" block below it. That gap is why the
verbatim rule was added. After the rule, a test on `gemini-3.7-flash`
returned the path exactly.

## At a glance

| # | Question | Tool chosen | Key result |
|---|---|---|---|
| 1 | Who owns payments-service? | `find_owner` | Riya Sharma, Payments team |
| 2 | Why is the settlement retry limit three? | `trace_decision` | DEC-001 replaced DEC-000 (five attempts) after incident INC-212; justified by RFC-47 and POSTMORTEM-212; implemented in PAY-1042 and PAY-1043 |
| 3 | What breaks if auth-service goes down? | `blast_radius` | api-gateway and payments-service (1 hop), notification-service (2 hops) |
| 4 | Who should review a change to payments-service? | `find_experts` + `find_owner` | Riya (owner, 48 commits) and Aman (107 commits across three projects); Priya from the Growth team surfaces too |
| 5 | Who should I ask about how audit events are written? | `who_to_ask` | Leila Hassan (owns audit-log, wrote ADR-09), then Victor Alves and Grace Lin |

## Full output

The document URLs (`wiki.acme.io`) belong to the fictional company in the
synthetic dataset and do not exist.

```text
Model: gemini-3.8-flash, paced to 5 requests/minute

> Who owns payments-service?
  → find_owner(system='payments-service')

========================================================================
Q: Who owns payments-service?
========================================================================
**payments-service** is owned by **Riya Sharma** (Staff Engineer) on the **Payments** team. The system is classified as **critical** tier.

### How I know this:
`(:Person {name: "Riya Sharma"})-[:OWNS]->(:System {name: "payments-service"})`  
`(:Person {name: "Riya Sharma"})-[:MEMBER_OF]->(:Team {name: "Payments"})`

--- graph traversals executed ---
  [find_owner] (Person:Riya Sharma)-[:OWNS]->(System:payments-service); (Person:Riya Sharma)-[:MEMBER_OF]->(Team:Payments)

> Why is the settlement retry limit three? What was it before, and what changed it?
  → trace_decision(topic='settlement retry limit')

========================================================================
Q: Why is the settlement retry limit three? What was it before, and what changed it?
========================================================================
The settlement retry limit was reduced to three attempts (with exponential backoff) to prevent retry storms that saturate the ledger database.

### What it was before and what changed it
* **Previous limit:** Under decision **DEC-000** (made July 15, 2023), settlement retries were capped at **five attempts**.
* **What changed it:** On April 1, 2025, Riya Sharma authored decision **DEC-001**, which superseded DEC-000 and lowered the cap from five to three attempts.
* **The trigger:** Incident **INC-212** (*"Ledger overload from payment retry storm"*, March 14, 2025), where downstream timeouts caused `payments-service` to retry five times per request. The resulting volume saturated `ledger-db` connections and caused 42 minutes of failed settlements.
* **Implementation:** Hardened via the `retry-hardening` project (tickets **PAY-1042** to cap retries at three and **PAY-1043** to add a dead letter queue).

---

### How I know this:
* **Path traversed:**
  `(Decision:DEC-001)-[:ABOUT]->(System:payments-service); (Person:Riya Sharma)-[:DECIDED]->(Decision:DEC-001); (Decision:DEC-001)-[:TRIGGERED_BY]->(Incident:INC-212); (Decision:DEC-001)-[:JUSTIFIED_BY]->(Document:RFC-47); (Decision:DEC-001)-[:JUSTIFIED_BY]->(Document:POSTMORTEM-212); (Document:ONBOARD-PAY)-[:REFERENCES]->(Document:RFC-47); (Document:RFC-52)-[:REFERENCES]->(Document:RFC-47); (Document:RFC-61)-[:REFERENCES]->(Document:RFC-47); (Document:RUNBOOK-PAY)-[:REFERENCES]->(Document:RFC-47); (Person:Riya Sharma)-[:WORKED_ON]->(Project:retry-hardening)-[:USES]->(System:payments-service); (Person:Riya Sharma)-[:REPORTED]->(Ticket:PAY-1042)-[:PART_OF]->(Project:retry-hardening); (Person:Aman Gupta)-[:REPORTED]->(Ticket:PAY-1043)-[:PART_OF]->(Project:retry-hardening); (Decision:DEC-001)-[:SUPERSEDES]->(Decision:DEC-000) | (Decision:DEC-000)-[:ABOUT]->(System:payments-service); (Person:Riya Sharma)-[:DECIDED]->(Decision:DEC-000)`

* **Documents:**
  * **RFC-47**: *"Bounded retries for payment settlement"* – [https://wiki.acme.io/rfc/47](https://wiki.acme.io/rfc/47)
  * **POSTMORTEM-212**: *"Postmortem: INC-212 ledger overload"* – [https://wiki.acme.io/pm/212](https://wiki.acme.io/pm/212)

--- graph traversals executed ---
  [trace_decision] (Decision:DEC-001)-[:ABOUT]->(System:payments-service); (Person:Riya Sharma)-[:DECIDED]->(Decision:DEC-001); (Decision:DEC-001)-[:TRIGGERED_BY]->(Incident:INC-212); (Decision:DEC-001)-[:JUSTIFIED_BY]->(Document:RFC-47); (Decision:DEC-001)-[:JUSTIFIED_BY]->(Document:POSTMORTEM-212); (Document:ONBOARD-PAY)-[:REFERENCES]->(Document:RFC-47); (Document:RFC-52)-[:REFERENCES]->(Document:RFC-47); (Document:RFC-61)-[:REFERENCES]->(Document:RFC-47); (Document:RUNBOOK-PAY)-[:REFERENCES]->(Document:RFC-47); (Person:Riya Sharma)-[:WORKED_ON]->(Project:retry-hardening)-[:USES]->(System:payments-service); (Person:Riya Sharma)-[:REPORTED]->(Ticket:PAY-1042)-[:PART_OF]->(Project:retry-hardening); (Person:Aman Gupta)-[:REPORTED]->(Ticket:PAY-1043)-[:PART_OF]->(Project:retry-hardening); (Decision:DEC-001)-[:SUPERSEDES]->(Decision:DEC-000) | (Decision:DEC-000)-[:ABOUT]->(System:payments-service); (Person:Riya Sharma)-[:DECIDED]->(Decision:DEC-000)

> What breaks if auth-service goes down?
  ... Gemini returned 503, waiting 10s (retry 1/4)
  → blast_radius(system='auth-service')

========================================================================
Q: What breaks if auth-service goes down?
========================================================================
If **auth-service** goes down, the following systems will be impacted:

* **Directly impacted (1 hop away):**
  * **api-gateway** (Tier: Critical) — owned by Daniel Okafor
  * **payments-service** (Tier: Critical) — owned by Riya Sharma

* **Transitively impacted (2 hops away):**
  * **notification-service** (Tier: Standard) — owned by Priya Nair

---

### How I know this:
* `(System:api-gateway)-[:DEPENDS_ON*1]->(System:auth-service) | (System:payments-service)-[:DEPENDS_ON*1]->(System:auth-service) | (System:notification-service)-[:DEPENDS_ON*2]->(System:auth-service)`

--- graph traversals executed ---
  [blast_radius] (System:api-gateway)-[:DEPENDS_ON*1]->(System:auth-service) | (System:payments-service)-[:DEPENDS_ON*1]->(System:auth-service) | (System:notification-service)-[:DEPENDS_ON*2]->(System:auth-service)

> Who should review a change to payments-service, and why them?
  → find_experts(system='payments-service')
  → find_owner(system='payments-service')

========================================================================
Q: Who should review a change to payments-service, and why them?
========================================================================
The best people to review a change to **payments-service** are:

1. **Riya Sharma** (Staff Engineer, Payments Team)
   - **Why:** She is the formal owner of `payments-service`, has 48 commits on related projects (`retry-hardening`), and has incident response experience on the service (`INC-212`).
2. **Aman Gupta** (Payments Team)
   - **Why:** He is the top hands-on contributor with 107 commits across multiple related projects (`retry-hardening`, `idempotency-keys`, and `notif-batching`), and served as a responder on multiple incidents affecting the service (`INC-212`, `INC-287`).

Depending on the scope of the change, other strong reviewers include:
- **Nikhil Rao** (Payments Team) – 41 commits on `retry-hardening` and `idempotency-keys`.
- **Priya Nair** (Growth Team) – 44 commits on `notif-batching` and responder on `INC-355`.

---

### How I know this:
- `(Person:Riya Sharma)-[:OWNS]->(System:payments-service); (Person:Riya Sharma)-[:MEMBER_OF]->(Team:Payments)`
- `(Person:Aman Gupta)-[:WORKED_ON]->(Project:retry-hardening/idempotency-keys/notif-batching)-[:USES]->(System:payments-service) [107 commits]`
- `(Person:Riya Sharma)-[:WORKED_ON]->(Project:retry-hardening)-[:USES]->(System:payments-service) [48 commits]`
- `(Person:Priya Nair)-[:WORKED_ON]->(Project:notif-batching)-[:USES]->(System:payments-service) [44 commits]`
- `(Person:Nikhil Rao)-[:WORKED_ON]->(Project:retry-hardening/idempotency-keys)-[:USES]->(System:payments-service) [41 commits]`
- `(Person:Jonas Weber)-[:WORKED_ON]->(Project:notif-batching)-[:USES]->(System:payments-service) [26 commits]`
- `(Person:Aman Gupta)-[:PARTICIPATED_IN]->(Incident:INC-212/INC-287)-[:AFFECTED]->(System:payments-service)`
- `(Person:Riya Sharma)-[:PARTICIPATED_IN]->(Incident:INC-212)-[:AFFECTED]->(System:payments-service)`
- `(Person:Priya Nair)-[:PARTICIPATED_IN]->(Incident:INC-355)-[:AFFECTED]->(System:payments-service)`
- `(Person:Omar Haddad)-[:PARTICIPATED_IN]->(Incident:INC-212)-[:AFFECTED]->(System:payments-service)`
- `(Person:Daniel Okafor)-[:PARTICIPATED_IN]->(Incident:INC-287)-[:AFFECTED]->(System:payments-service)`
- `(Person:Ines Duarte)-[:PARTICIPATED_IN]->(Incident:INC-287)-[:AFFECTED]->(System:payments-service)`
- `(Person:Kofi Mensah)-[:PARTICIPATED_IN]->(Incident:INC-355)-[:AFFECTED]->(System:payments-service)`

--- graph traversals executed ---
  [find_experts] (Person:Aman Gupta)-[:WORKED_ON]->(Project:retry-hardening/idempotency-keys/notif-batching)-[:USES]->(System:payments-service)  [107 commits] | (Person:Riya Sharma)-[:WORKED_ON]->(Project:retry-hardening)-[:USES]->(System:payments-service)  [48 commits] | (Person:Priya Nair)-[:WORKED_ON]->(Project:notif-batching)-[:USES]->(System:payments-service)  [44 commits] | (Person:Nikhil Rao)-[:WORKED_ON]->(Project:retry-hardening/idempotency-keys)-[:USES]->(System:payments-service)  [41 commits] | (Person:Jonas Weber)-[:WORKED_ON]->(Project:notif-batching)-[:USES]->(System:payments-service)  [26 commits] | (Person:Priya Nair)-[:PARTICIPATED_IN]->(Incident:INC-355)-[:AFFECTED]->(System:payments-service) | (Person:Omar Haddad)-[:PARTICIPATED_IN]->(Incident:INC-212)-[:AFFECTED]->(System:payments-service) | (Person:Aman Gupta)-[:PARTICIPATED_IN]->(Incident:INC-212/INC-287)-[:AFFECTED]->(System:payments-service) | (Person:Daniel Okafor)-[:PARTICIPATED_IN]->(Incident:INC-287)-[:AFFECTED]->(System:payments-service) | (Person:Ines Duarte)-[:PARTICIPATED_IN]->(Incident:INC-287)-[:AFFECTED]->(System:payments-service) | (Person:Kofi Mensah)-[:PARTICIPATED_IN]->(Incident:INC-355)-[:AFFECTED]->(System:payments-service) | (Person:Riya Sharma)-[:PARTICIPATED_IN]->(Incident:INC-212)-[:AFFECTED]->(System:payments-service)
  [find_owner] (Person:Riya Sharma)-[:OWNS]->(System:payments-service); (Person:Riya Sharma)-[:MEMBER_OF]->(Team:Payments)

> Who should I ask about how audit events are written?
  → who_to_ask(topic='audit events')

========================================================================
Q: Who should I ask about how audit events are written?
========================================================================
You should ask **Leila Hassan** (`leila.hassan@acme.io`) on the **Data** team. She owns `audit-log`, authored **ADR-09 (Audit events written asynchronously)**, and worked on the `audit-pipeline` project.

Other team members with hands-on experience on `audit-pipeline` are **Victor Alves** (`victor.alves@acme.io`) and **Grace Lin** (`grace.lin@acme.io`).

### How I know this:
- **Path:**
  - `(Person:Leila Hassan)-[:OWNS]->(System:audit-log)`
  - `(Person:Leila Hassan)-[:AUTHORED]->(Document:ADR-09)`
  - `(Person:Leila Hassan)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db)`
  - `(Person:Victor Alves)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db)`
  - `(Person:Grace Lin)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db)`
- **Documents:** ADR-09 ("Audit events written asynchronously")

--- graph traversals executed ---
  [who_to_ask] (Person:Leila Hassan)-[:OWNS]->(System:audit-log); (Person:Leila Hassan)-[:AUTHORED]->(Document:ADR-09); (Person:Leila Hassan)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db) | (Person:Victor Alves)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db) | (Person:Grace Lin)-[:WORKED_ON]->(Project:audit-pipeline)-[:USES]->(System:audit-log/ledger-db)

Demo finished: 5/5 questions answered in 2m 15s.
```

## Reproduce it

See [README.md](README.md#setup). A full run makes about 11 Gemini requests
and takes 2–3 minutes on the free tier. Free-tier keys are also limited to
20 requests per day per model ([STATE.md](STATE.md#gemini)). Gemini's wording
will differ slightly between runs; the tools and paths will not, because they
come from fixed Cypher queries over fixed data.
