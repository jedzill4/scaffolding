# Engineering Standards — CES (Collective Engineering Standard)

Single source of truth for how house engineering rules are coded, cited, and shipped.
`AGENTS.md` and `README.md` reference this file rather than restating it.

## What a CES is

A **CES — Collective Engineering Standard** is one house rule that the scaffolder ships into
target repos (as an ast-grep rule, a prek hook, a `pyproject` setting, or an AGENTS.md
directive + detail file). Each standard is tracked by exactly one issue on the
[`jedzill4/scaffolding`](https://github.com/jedzill4/scaffolding/issues) tracker, which is the
SSOT for that rule's text and review state.

## Two identifiers, two jobs

| Layer | Value | Used in |
|---|---|---|
| **Catalog code** | `CES-<issue#>` | AGENTS.md index, commit/PR refs, human citation, violation messages |
| **Machine id** | kebab-case **slug** (`log-no-print`, `api-schemas-extra-forbid`) | ast-grep `id:`, prek hook id, `.agents/rules/<slug>.md`, `# ast-grep-ignore: <slug>` |

Always written together where space allows: **`CES-46 · log-no-print`**.

Never encode the CES number in the machine id — slugs are what tooling and suppressions key
on, so they must stay stable and semantic.

## Invariants

- **Every CES has a tracker issue.** No rule gets a code by existing only in code.
- **One CES = one standard.** A standard may ship **multiple slugs** — e.g. `CES-79` ships the
  four `no-dict-*` ast-grep patterns; an architecture rule may ship an ast-grep rule *and* an
  import-linter contract under the same CES.
- **Number source = the issue id.** Gaps from declined proposals are expected and meaningful
  (PEP/RFC-style — a rejected number is never reused).
- **Already-implemented rules get a retroactive AS-BUILT issue** so they satisfy the invariant.
  Mark the issue body `AS-BUILT` and assign no new enforcement work beyond CES wiring.

## Violation messages embed the code

```yaml
message: "CES-46 (log-no-print): libraries log, they don't print — use the house get_logger."
```

The slug remains the suppression key (`# ast-grep-ignore: <slug>`), so embedding the code in
the message text never affects tooling stability.

### Messages are self-contained (no cross-rule references)

A violation message states **its own** rule, the fix, and its CES code — nothing else. It must
**not**:

- name a sibling rule (e.g. "hidden from the no-dict-return rules"), or
- prescribe another rule's suppression key (a message for `no-dict-alias` telling you to add
  `# ast-grep-ignore: no-dict-return-annotation` is wrong — and wouldn't even silence itself).

Scattering policy across sibling messages is context-poisoning: one rule ends up restating or
superseding another's decision. The grouped rationale, the relationships between a standard's
slugs, and the escape-hatch mechanism live **once**, in the standard's detail file
(`.agents/rules/<slug>.md`) — the single source of truth. If a message needs more than "what +
fix + code", that belongs in the detail file, not the message.

## Where the pieces live (in a target repo)

- **Always-on index:** a marker-delimited `## Engineering Standards` section in `AGENTS.md`
  listing every rule (terse directive + `[ast-grep]`/`[prek]`/`[judgment]` marker + an
  `@.agents/rules/<slug>.md` pointer).
- **On-demand detail:** `.agents/rules/<slug>.md` — full rationale, examples, migration.
- **Canonical code:** `.agents/snippets/` — drop-ins for new repos, comparison templates for existing
  ones.

(Rationale for index-in-AGENTS.md over packaged skills: passive always-on context outperforms
on-demand retrieval for horizontal standards — see PRD #78.)

## Catalog of AS-BUILT codes

Rules already shipped before the CES scheme, now coded via retroactive issues:

| CES | Slugs | Ships as |
|---|---|---|
| **CES-79** | `no-dict-return-annotation`, `no-dict-call-return`, `no-dict-literal-return`, `no-dict-alias` | ast-grep (`templates/ast-grep-rules/no-dict-*.yml`) |
| **CES-71** | `file-size-guard` | prek hook (`templates/prek-python.toml`, 400 warn / 700 error) |

## References

- Roll-out plan: **PRD #78** (`meta/standards-integration`).
- Per-rule state: the tracker issue for each `CES-<id>`.
