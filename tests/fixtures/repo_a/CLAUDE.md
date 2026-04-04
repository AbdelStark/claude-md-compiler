
# CLAUDE.md

General repo guidance.

```cldc
rules:
  - id: generated-lock
    kind: deny_write
    mode: block
    paths: ["generated/**"]
    message: Do not touch generated files.
```
