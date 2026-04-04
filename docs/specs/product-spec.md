# claude-md-compiler

    Compile CLAUDE.md into enforceable repo policy for Claude Code.

    ## Product thesis
    Turn CLAUDE.md from a passive instruction document into an active, versioned execution contract enforced across local runs, CI, and agent workflows.

    ## Problem statement
    - CLAUDE.md is advisory, not executable.
- Teams cannot tell which instructions are hard constraints versus soft guidance.
- Coding agents drift on architecture, generated files, test requirements, and repo-specific rituals.
- Reviewers discover violations late, after the agent has already made a mess.

    ## Target users
    - Staff engineers operating Claude Code in large repos
- Infra / platform teams defining repo policy
- Tech leads who want agents to stay inside architectural lanes
- OSS maintainers who want contributor automation without chaos

    ## Design principles
    - Local-first by default. Teams should be able to run the product without handing source code or transcripts to a hosted service.
    - Repo-aware, not generic. The product should care about path structure, conventions, coupling, and workflow shape.
    - Explainable output. Every warning, block, score, or ranking must explain what triggered it.
    - Graceful degraded mode. Partial data should still yield useful output instead of a useless hard failure.
    - Thin core, strong contracts. Prefer sharp schemas, deterministic artifacts, and explicit extension points over magic.

    ## MVP
    - Parse CLAUDE.md plus optional .claude-compiler.yaml and policies/*.yml
- Compile rules into .claude/policy.lock.json
- Evaluate edits, commands, and touched files against compiled policy
- Support observe, warn, block, and fix modes
- Ship as local CLI plus CI command

    ## Repo layout
    ```text
    docs/
  specs/product-spec.md
  rfcs/
src/
  cldc/
    cli/
    ingest/
    parser/
    compiler/
    policy/
    repo/
    runtime/
    report/
examples/
tests/
    ```

    ## CLI surface
    - cldc compile
- cldc check
- cldc explain
- cldc doctor
- cldc fix
- cldc ci

    ## Detailed architecture
    The implementation should be split into a pure core and a thin shell.

    Core responsibilities:
    - ingest source inputs and normalize them into canonical records
    - build an internal model that can be serialized, diffed, and tested
    - run deterministic evaluation logic over repo state, transcript evidence, and policy/config inputs
    - emit machine-readable artifacts first, then render human-facing summaries from those artifacts

    Shell responsibilities:
    - CLI argument parsing
    - git integration
    - GitHub / CI adapters
    - rich terminal output
    - report publishing and file export

    ## Failure modes
    - malformed input files
    - stale compiled artifacts or schema drift
    - partial repo scans or missing transcript coverage
    - giant monorepos causing performance blowups
    - ambiguous matches that should lower confidence instead of pretending certainty
    - user confusion when the tool is too clever and too opaque

    ## Trust and UX rules
    - never claim more certainty than the evidence supports
    - keep JSON output stable and versioned
    - keep terminal output blunt and actionable
    - prefer one recommended next action over generic laundry lists
    - expose provenance for every major conclusion

    ## Roadmap
    ### Phase 1
    Nail local CLI, schema stability, and deterministic artifact generation.

    ### Phase 2
    Add GitHub-native workflows, richer repo heuristics, and preset packs for common codebase shapes.

    ### Phase 3
    Add plugin surfaces, richer report rendering, and multi-team operational features.

    ## Non-goals
    - becoming a general-purpose IDE
    - replacing human code review or repo ownership
    - supporting every agent runtime from day one
    - building a hosted analytics platform before the local core is solid

    ## Success metrics
    - time-to-value: repo gets useful output in under 10 minutes
    - false-positive rate stays low enough that teams keep the tool enabled
    - repeated use in local workflows and CI, not just demo runs
    - output is referenced directly in review or policy conversations

    ## Initial build sequence
    1. RFC 0001 to 0003: schemas, ingestion, canonical artifacts
    2. RFC 0004 to 0006: repo or diff modeling plus core evaluation logic
    3. RFC 0007 to 0009: runtime/CLI/UX
    4. RFC 0010 onward: integrations, presets, and governance
