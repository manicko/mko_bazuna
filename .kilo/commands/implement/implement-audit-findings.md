---
name: implement-audit-findings
description: Execute validated audit findings safely — risk-assess, research alternatives, select best route, plan tests/docs, implement, and update documentation
agent: orchestrator
alwaysApply: false
---

# Workflow

## Step 1 — Study Findings

Summarize all validated findings from the audit report provided at the end of this prompt.
Group by severity (CRITICAL → HIGH → MEDIUM → LOW / Advisory).
Do not argue on the workflow, just follow.

## Step 2 — Risk & Complexity Triage (Researcher)

Use `<task>` tool to launch one or more `<researcher>` agents to classify every finding:

| Category | Criteria | Action |
|----------|----------|--------|
| **Simple / Low-risk** | Trivial change, single clear fix, no architecture impact, no alternatives | Proceed directly to implementation |
| **Complex / High-risk** | Multi-file, architectural impact, data migration, infra change, or behavioral risk | Full research required |
| **Multiple viable routes** | More than one correct solution exists | Full research required |


## Step 2.1 — Research Remediation Paths

For **Complex** and **Multiple-routes** findings only,
Use `<task>` tool to launch one or more `<researcher>` agents to:

1. Investigate project architecture relevant to the finding
2. Enumerate **all** alternative solutions (not only the audit recommendation)
3. Evaluate each alternative on:
   - Correctness & security
   - Fit with existing architecture and patterns
   - Maintainability, future evolution, and developer ergonomics
   - Rollout risk and rollback ease
4. Select **exactly one** preferred solution
5. Document rationale and rejected alternatives

Prefer solid, future-proof solutions over quick patches.

## Step 3 — Tests & Documentation Requirements (Researcher)

After the fix path is fixed for **every** finding, launch `<researcher>` agent(s) to produce, per finding:

- **Tests required** (happy path + key edge/error cases; integration preferred over pure unit)
- **Docs required** (spec, architecture, ops, agent docs, README, comments — list exact files/sections or “none”)

Save the consolidated matrix to:
`.ai/plans/{Number}_{audit_phase}_fix_matrix.md`

## Step 4 — Implementation (Implementor)

For each finding (or coherent batch of independent findings), use `<task>` tool to launch `<implementor>` agent with:

1. Exact scope and chosen solution
2. Required tests
3. Quality gates:

   **Python (`*.py`):**
   - `uv run ruff check <affected>`
   - `uv run mypy <affected>`
   - `uv run basedpyright <affected>`
   - `uv run pytest <relevant_path>`

4. Conventional commit (specific files only):

   ```bash
   git add <specific-files>
   git commit -m "fix({scope}): {short_description}" -m "Task: {TASK_FILE_NAME}"
   ```

### Git Rules (strict)

Forbidden (no exceptions):
`git reset`, `git checkout`, `git clean`, `git stash`, `git rebase`,
`git push --force`, `git branch -D`, `git tag -d`, `git commit --amend`,
`git revert`, `git mv`, `git rm`, `git cherry-pick`

To undo → edit + new commit. Never rewrite history.

## Step 5 — Documentation (Doc-specialist)

After successful implementation of a finding (or batch), launch `<doc-specialist>` agent with the exact list of documentation changes identified in Step 3.

Doc-specialist must:
- Update only the listed files/sections
- Keep language consistent with existing docs
- Mark any obsolete claims as resolved

## Step 6 — Completion

- Mark each finding as done in the matrix
- Move completed plan files to `.ai/plans/done`
- Ensure no unrelated refactors or speculative changes remain

---

# Expected Result

- Every validated finding (including advisory) processed
- Complex / multi-route findings researched; single best solution selected
- Tests written and passing for non-trivial changes
- Lint / type checks passing for changed code
- Documentation updated where required
- Conventional commits created
- Architecture preserved; minimal, future-proof fixes preferred

---

Audit report path / content:
