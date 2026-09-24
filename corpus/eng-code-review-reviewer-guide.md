---
doc_id: eng-code-review-reviewer-guide
title: Code Review Guide for Reviewers
doc_kind: standalone
version: null
effective_date: 2026-07-13
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# Code Review Guide for Reviewers

The Code Review Process sets out the rules every pull request must follow.
This guide goes further and explains how to review well. It is written for
engineers who have recently started reviewing, but experienced reviewers
may find it a useful reminder.

## Why we review
Code review has three goals, in this order:

1. **Catch problems** before they reach production: bugs, security issues,
   missing tests and changes that will be hard to operate.
2. **Share knowledge** so that more than one person understands each part of
   the system.
3. **Keep the codebase consistent** so it stays easy to read and change.

Review is not a gate to show that you are more senior than the author, and
it is not a place to redesign a feature that has already been agreed.

## Before you start
- Read the pull request description and the linked ticket first. You cannot
  judge a change without knowing what it is meant to do.
- Check that CI has passed. If it has not, you can usually wait until it
  does before reviewing in detail.
- If the change is too large to review properly, say so politely and ask
  the author to split it. A review that skims a very large change catches
  little.

## What to look at
Work from the most important questions to the least important.

**Does it do the right thing?**
Does the change solve the problem in the ticket? Are there cases the author
has not handled, such as empty input, errors from other services, retries or
concurrent requests?

**Is it safe?**
Look for user input that reaches a database query or a shell command
unchecked, secrets in code or logs, personal data written to logs, and
permission checks that are missing. When in doubt, ask the security team to
review.

**Is it tested?**
New behaviour needs tests. Bug fixes need a test that fails without the fix.
Read the tests as carefully as the code: a test that cannot fail is worse
than no test.

**Can we run it?**
Will the on-call engineer understand what went wrong from the logs and
metrics? Does the change need a feature flag, a migration or an update to a
runbook? Is it backwards compatible with the version currently running?

**Is it clear?**
Are names clear? Is there a simpler way to write it? Would a short comment
help the next reader understand *why* the code is written this way?

**Does it follow our conventions?**
Formatting and most style rules are checked by linters in CI, so do not
spend review time on them. Comment only on conventions that tools cannot
check.

## Writing comments
- Be specific. "This loop will run once per user, so it makes one database
  call per user" is more useful than "this looks slow".
- Explain why. If you ask for a change, say what problem it solves.
- Ask questions when you are not sure. "What happens if this list is empty?"
  invites the author to explain, and you may learn something.
- Mark the weight of each comment. Use `nit:` for minor suggestions the
  author may ignore, and say clearly when something must change before
  merge.
- Praise good work. Pointing out a well-written test or a clear abstraction
  is part of sharing knowledge too.
- Keep the tone neutral. Written comments read more harshly than spoken
  ones. Write "we" and "this code", not "you".

## Approving, commenting or requesting changes
- **Approve** when the change is ready to merge, even if you left a few
  nits. Trust the author to deal with them.
- **Comment** when you have questions but have not finished reviewing, or
  when you are not a code owner.
- **Request changes** only for problems that must be fixed before merge. When
  the author has addressed them, review again promptly and approve.

## When you disagree
If you and the author cannot agree after a couple of exchanges, move the
discussion to a call or to your team channel. If you still disagree, ask
your tech lead to decide. Record the decision in the pull request so others
can see it later. Disagreements about style that no written convention
covers should usually go the author's way.

## Looking after your own time
- Review in focused blocks instead of dipping in and out all day.
- Reply to review requests within the response time in the Code Review
  Process, even if only to say when you will get to it.
- If you are assigned a review you cannot do, reassign it rather than
  leaving it waiting.
