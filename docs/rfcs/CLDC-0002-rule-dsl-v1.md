# CLDC-0002: Rule DSL v1

    **Status:** Draft  
    **Author:** Hermes  
    **Dependencies:** CLDC-0001

    ## Why this exists
    Define the authoring language for required reads, forbidden writes, coupled changes, command gates, and generated-file protection.

    ## Scope
    - path selectors
- rule ids
- conditions
- severity
- mode overrides

    ## Detailed design
    - Human-readable YAML DSL
- Schema validation
- Examples for Python/Rust/TS repos

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
