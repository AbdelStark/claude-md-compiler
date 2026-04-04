# CLDC-0012: Preset packs

    **Status:** Draft  
    **Author:** Hermes  
    **Dependencies:** CLDC-0002, CLDC-0009

    ## Why this exists
    Ship batteries-included rule packs for common repo archetypes.

    ## Scope
    - python-service
- rust-workspace
- ts-monorepo

    ## Detailed design
    - Easy onboarding
- Override support

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
