---
doc_id: eng-ci-pipeline-faq
title: CI Pipeline FAQ
doc_kind: standalone
version: null
effective_date: 2026-05-11
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# CI Pipeline FAQ

Answers to common questions about the continuous integration (CI) pipeline
that runs on every pull request.

**What does the pipeline run?**
Four stages, in order: lint, unit tests, build, and integration tests. The
build stage produces a container image that is pushed to the internal
registry. A stage only starts if the one before it passed.

**Why did my pipeline not start?**
Pipelines start when you push to a branch that has an open pull request. Draft
pull requests run lint and unit tests only. If nothing starts, check that the
repository has a `.ci.yml` file on your branch.

**A test failed but passes on my laptop. What now?**
First re-run the failed job once from the pull request page. If it passes on
re-run, the test is probably flaky: report it in #ci-help with a link to the
failed run so the owning team can fix it. Do not keep re-running until it
goes green.

**How do I see the logs?**
Click the failed check on the pull request, then **Details**. Logs are kept
for 90 days.

**Can I skip CI for a small change?**
No. Documentation-only changes run a shorter pipeline automatically, based on
the paths changed, but no change can skip CI entirely.

**Why is my pipeline queued?**
Runners are shared across all teams. Queues are longest in the late IST
afternoon. If a job has been queued for an unusually long time, post in
#ci-help.

**How do I add a secret to the pipeline?**
Never commit secrets to the repository. Ask your team lead to add the secret
in the CI settings for your repository. It is then available to jobs as an
environment variable.

**Who owns the pipeline?**
The Developer Experience team owns the shared pipeline templates. Your team
owns the `.ci.yml` file in its own repositories.
