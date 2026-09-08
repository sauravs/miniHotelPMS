---
name: qa-log
description: Answer a question about this project and append both the question and the answer to docs/QA.md as a permanent, numbered transcript entry. Use when the user invokes /qa-log, or asks to "log this answer", "add this to QA", or "record this Q&A".
---

# qa-log — answer, then record it

The project keeps a **running Q&A transcript** with the project owner in `docs/QA.md`. It is not a
FAQ and not a summary: it is the record of what was asked, what was answered, and what was known at
the time. It is one of the seven documents a cold session reads to get oriented, and several
decisions in `docs/context.md` trace back to an entry in it.

## What to do

1. **Answer the question properly first.** The log is a side effect, never a substitute. Give the
   full answer in the conversation as you normally would — the same depth, the same evidence, the
   same willingness to say "I don't know".

2. **Then append it to `docs/QA.md`**, using the format below. Append only; never rewrite or tidy an
   earlier entry. If a later answer corrects an earlier one, write a **new entry** that says so and
   links back — the fact that we were wrong on the 4th is part of the record.

3. **Confirm in one line** what was logged and where: `Logged as Q13 in docs/QA.md.`

## Entry format

Append to the end of `docs/QA.md`:

```markdown
---

## Q<n> — <YYYY-MM-DD>

**Q:** <the user's question, verbatim. Do not paraphrase, tidy or shorten it — the exact wording
is often the point, and a paraphrase quietly changes what was asked.>

**A:**

<the answer, in full. Keep the structure that made it readable — headings, tables, code blocks.
Trim only conversational scaffolding ("Sure!", "Let me check…") and tool-call narration.>

**Evidence:** <files read, commands run, fixtures inspected — or `reasoning only, nothing verified`.
Be exact. An answer that was reasoned rather than checked must say so.>

**Status:** <one of: `answered` · `answered, needs confirmation from the lead` ·
`open — see docs/open-questions.md §N` · `superseded by Q<m>`>
```

## Rules

- **Number sequentially.** Read the last `## Q<n>` heading in `docs/QA.md` and use `n + 1`. Never
  reuse or renumber.
- **Use today's date**, ISO format.
- **Verbatim question.** Always.
- **Never silently edit history.** A correction is a new entry plus a `Status: superseded by Q<m>`
  line added to the old one. That single added line is the only permitted edit to a past entry.
- **Be honest about what was checked.** This project's central rule is that it does not manufacture
  confidence. An answer that came from reading documentation rather than running code must say so —
  documentation review got 4 of 12 risks wrong here, which is exactly why the field exists.
- **If the answer raises a genuinely open question**, add it to `docs/open-questions.md` as well and
  cross-reference it from the `Status` line. The QA log is a transcript; the open-questions file is
  the working list.
- **No credentials, no guest personal data** in the log. Refer to a reservation by its id.
- If `docs/QA.md` does not exist, create it with the header from the current file and start at `Q1`.
