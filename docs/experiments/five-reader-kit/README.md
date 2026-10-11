# Five-reader kit (issue #61)

Operator pack for the frozen protocol in
[`../distribution-five-reader.md`](../distribution-five-reader.md).
**Nothing here has been sent to anyone.** Review it first; you send messages
yourself.

This folder does not change the protocol. Where the kit needs a wording the
protocol never wrote (invite text, a time box, a scoring rubric), that is
called out below and left empty of invented numbers.

## Who runs it

You (Gianluca). Five people you already know, in roles where a declarative
LLM-state-machine DSL with a self-authoring console would plausibly land — the
same kind of people the protocol already names (colleague who ships agent
products, friend who uses Claude/Cursor daily, and so on). Write **roles, not
names**, in the register.

## What you send (per reader)

One message. Copy the language that matches the reader:

| Send | Do not send |
| --- | --- |
| [`invite-en.md`](invite-en.md) or [`invite-it.md`](invite-it.md) | this README |
| the matching half of [`task.md`](task.md) | [`questions.md`](questions.md) |
| the two links in [`materials.md`](materials.md) | [`response-form.md`](response-form.md) |
| | any other repo page (ADRs, getting started, `what-mklang-is`, examples) |

The protocol allows **only** the repository README and the two demo recordings
(`agent`, `language` — see [`docs/demos.md`](../../demos.md)).

## Time per reader

The protocol does not set a time box. The only durations already recorded in
the repo are the two demo files in `docs/assets/demos/manifest.json`:

| Recording | Duration already in the manifest |
| --- | --- |
| `agent` | 21.92 seconds |
| `language` | 11.84 seconds |

There is no in-repo reading-time figure for the README. After they look, you
write down their first question. The install note is **optional**, and the
protocol's window for it is 24 hours.

## How you run one session

1. Open the protocol. Do not alter its steps, metric, or register columns.
2. Pick the next person. Label them by role (for example: "colleague, ships
   agent products"), never by name.
3. Send **only** the invite + task + the two material links. Do not explain
   what mklang is, what it is for, or how it compares to anything.
4. Wait. If they ask you to explain before looking, repeat: look at the two
   links first, then send the first question that comes to mind.
5. Copy their **first question verbatim** into [`response-form.md`](response-form.md).
   Do not paraphrase. Keep their language (English, Italian, or mixed).
6. After that first question is written down — not before — you may talk
   normally. Talking earlier voids the row.
7. Mark **Understood "for"?** yourself. The protocol asks this judgement and
   does not define a rubric. Do not add extra quiz questions to invent one.
8. Optionally, after 24 hours, mark whether they installed or tried anything.
   If you do not check, leave that cell empty.
9. Paste the filled row into the protocol's results register when you are
   ready to record the run. This kit does not fill the register.

Repeat until five valid rows exist. A row is valid only if they were shown
those two materials and you did not explain before the first question.

## After five rows

Fill the protocol headline, using only its words:

`n/5 understood · n/5 tried · branch: —`

Then apply the protocol's three branches. Do not add a fourth.

| Outcome (from the protocol) | Interpretation (from the protocol) |
| --- | --- |
| ≥3 of 5 **do not** understand what mklang is *for* after README + demos | Positioning problem; no coverage ratcheting touches it. |
| ≥3 understand, but **nobody** tries it | The thing it does best (agents authoring verified deterministic workflows, ADR 0015) is buried in ADRs, absent from the pitch. |
| ≥3 understand **and** ≥1 installs | Distribution is working; the repo is simply young (falsifier of the "structural distribution failure" claim). |

## Files in this kit

| File | Audience | Purpose |
| --- | --- | --- |
| [`invite-en.md`](invite-en.md) | reader | Short English invitation |
| [`invite-it.md`](invite-it.md) | reader | Same invitation in Italian |
| [`task.md`](task.md) | reader | EN + IT task (look, then first question) |
| [`materials.md`](materials.md) | you | Exact files and links the reader may get |
| [`questions.md`](questions.md) | you | Operator questions that fill the register |
| [`response-form.md`](response-form.md) | you | Copy-paste form + one register row |

## Related

- Protocol: [`../distribution-five-reader.md`](../distribution-five-reader.md)
- Issue #61
- ADR 0028 (product confidence stays provisional until the register is filled)
