# cldc RFCs

This directory holds the **frozen implementation contracts** for `cldc` —
the schemas, rule kinds, and packaged assets that consumers are allowed to
depend on. RFCs are not aspirational. They describe behavior that the code
already honors, so the runtime can safely refuse to load any artifact that
drifts away from them.

## Status taxonomy

| Status       | Meaning                                                                 |
|--------------|-------------------------------------------------------------------------|
| `Draft`      | Proposed contract under review. Not yet enforced by the code.           |
| `Frozen`     | Enforced contract. The code refuses to silently degrade.                |
| `Superseded` | Replaced by a newer RFC. Kept for archaeology, not for new consumers.   |

A `Frozen` RFC is the source of truth. If the code disagrees, the code is
wrong.

## Numbering and naming

RFCs use the prefix `CLDC-` followed by a four-digit sequence, in the
order they were merged. Filenames follow `CLDC-NNNN-short-slug.md`.
Numbers are never reused.

| Number       | Title                                              |
|--------------|----------------------------------------------------|
| CLDC-0001    | Policy lockfile                                    |
| CLDC-0002    | Check report                                       |
| CLDC-0003    | Fix plan                                           |
| CLDC-0004    | `require_claim` rule                               |
| CLDC-0005    | Preset packs                                       |

## Versioning rules

Each contract that emits JSON exposes two version markers:

- `$schema` — a URL of the form `https://cldc.dev/schemas/<artifact>/v<major>`.
  A change to this URL is a **hard break**: old consumers must reject the
  payload outright.
- `format_version` — a string of the form `"<minor>"`. A change to this
  field is a **soft break**: payloads with the same `$schema` URL but a
  different `format_version` are still recognizably this contract, but
  consumers must refresh themselves before trusting them.

Concretely, if you change a frozen RFC:

1. Append-only additions that keep every existing key intact and add new
   keys with explicit defaults bump `format_version` only.
2. Removing or repurposing a key, or changing its type, requires a new
   `$schema` URL (`v2`) and a new RFC that supersedes the old one.

## How to add or change an RFC

1. Open a PR that drops a new file under `docs/rfcs/` with `Status: Draft`
   and the next sequential number. Reference the implementation that will
   land alongside it.
2. Land the implementation and the RFC in the same merge. Flip the status
   to `Frozen` in that same PR.
3. To revise a frozen RFC, write a new RFC that supersedes it. Update the
   old file's header to `Status: Superseded` and set `Superseded by` to
   the new number. Do not edit the old contract in place except to fix
   typos that do not change meaning.

## What lives outside RFCs

Everything that is not a contract: error message wording, text/markdown
rendering, CLI flag spellings, internal Python module layout, and the
exact set of warnings emitted by `cldc doctor`. These are subject to
change without an RFC.

## Where to look first

- `CLDC-0001` for what `.claude/policy.lock.json` is allowed to contain.
- `CLDC-0002` for what `cldc check` and `cldc ci` are allowed to emit.
- `CLDC-0003` for what `cldc fix` is allowed to emit.
- `CLDC-0004` for the `require_claim` rule and how claims flow into the
  evaluator.
- `CLDC-0005` for how bundled preset packs are discovered, named, and
  merged.
