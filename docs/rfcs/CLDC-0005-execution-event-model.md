# CLDC-0005: Execution event model

    **Status:** Draft  
    **Author:** Hermes  
    **Dependencies:** CLDC-0003

    ## Why this exists
    Represent agent actions as policy-checkable events over reads, writes, diffs, commands, and completion claims.

    ## Scope
    - read event
- write event
- command event
- claim event

    ## Detailed design
    - Canonical event schema
- Batch evaluation support

    ## File and module impact
    - Add or update the canonical schema and parser surface for this RFC.
    - Add focused unit tests for success paths, malformed inputs, and degraded behavior.
    - Add one integration fixture proving this RFC works with neighboring components.

    ## Acceptance criteria
    - The behavior defined here is represented in a stable schema or interface.
    - The repo contains executable tests or fixtures for both happy path and failure path behavior.
    - Output produced by this RFC is deterministic given the same inputs.
    - The CLI or API surface documents how operators use this feature.
    - The resulting artifact is explainable enough that a reviewer can tell what happened and why.

    ## Notes for implementation
    - Keep the first version narrow.
    - Avoid hidden heuristics with no provenance trail.
    - Prefer explicit machine-readable artifacts over terminal-only behavior.
