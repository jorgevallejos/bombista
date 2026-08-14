---
description: Package validated work into a clean commit and pull request, running all checks first.
---

You are acting as the release manager for this project. The user has validated a piece of work and wants you to take it from here.

## Context from the user

$ARGUMENTS

**Arguments are optional.** Handle both cases:

- **If the user provided a description after `/release`**, use it as the authoritative intent for the commit message and PR title/body. The diff is still your source of truth for what actually changed — if the description and the diff disagree, point that out to the user before proceeding.

- **If the user ran a bare `/release` with no description**, do NOT ask for one. Derive the full story from the repository itself:
  - Run `git status` and `git diff` (for unstaged/staged changes) or `git log main..HEAD` and `git diff main...HEAD` (if changes are already committed on a feature branch).
  - Read the changed files in enough depth to understand the intent — not just the lines that changed.
  - From that, infer: the *type* of change (feat/fix/refactor/etc.), the *scope* (which module), and the *why* (what problem it solves or what it enables).
  - When suggesting a feature branch name and drafting the commit message, base them on this inferred intent.
  - Present your inferred summary to the user as part of the branch-confirmation step in step 1 (e.g. *"Based on the diff, this looks like a fix to the serializer's monotonicity check. Proceed?"*) so the user can correct you before any commit is made.

## Your job

Take the currently staged/unstaged changes (or the current branch if changes are already committed) and ship them to GitHub as a pull request, following the steps below. Stop and ask the user before proceeding if anything unexpected comes up (unrelated changes, failing tests, merge conflicts, etc.).

## What counts as a releasable change

Treat all of the following as legitimate, releasable project artifacts:

- Source code anywhere under `bombista/`, `tests/`, `docs/`, `scripts/`
- Project metadata: `pyproject.toml`, `.gitignore`, `README.md`
- Repo-level `CLAUDE.md`
- **`.claude/commands/*.md`** — shared Claude Code slash commands
- **`.claude/settings.json`** — shared Claude Code project settings

The only `.claude/` paths that are intentionally local-only (and gitignored) are `.claude/settings.local.json` and `.claude/sessions/`. Exclude them from staging.

## Release checklist

Execute these steps in order. Report results as you go. Do NOT skip steps.

1. **Snapshot the state**
   - Run `git status` and `git diff` to see what will be included.
   - Run `git branch --show-current` and `git branch -a` (briefly) so you and the user can see the current branch and other local branches.
   - **Always confirm the branch with the user before committing or pushing**, regardless of which branch is checked out. Show:
     - The current branch name.
     - Whether it tracks a remote, and whether it's ahead/behind.
     - A suggested feature branch name derived from the change description (kebab-case, max 40 chars, no special chars), in case the user wants to create one.
   - Ask the branch question in **two steps** for simplicity. Do NOT combine them into a single multi-part question.

     **Step 1 — simple Yes/No confirmation.** Ask: *"Commit to `<recommended-branch>`? (Yes / No)"*
       - If the user is currently on `main` or `master`, `<recommended-branch>` is the **suggested new feature branch** (kebab-case, type-prefixed like `chore/…` or `feat/…`, max 40 chars, derived from the inferred intent). Never recommend committing directly to `main` or `master`.
       - If the user is already on a feature branch, `<recommended-branch>` is the **current branch**.

     **Step 2 — only if the user answered No.** Ask: *"Which branch should I use instead? You can give a new branch name (I'll create it) or name an existing branch."*

   - Only proceed once the user has explicitly confirmed a target branch. If the target doesn't exist locally, create it with `git checkout -b <name>` before any commit.

2. **Run the full test suite**
   - Run `python -m pytest`.
   - If any test fails (other than the intentional red test), stop. Report which tests failed and ask the user how to proceed. Do not attempt to fix tests unless the user asks.

3. **Run a lint check** (once a linter is configured — skip this step if none is set up yet)

4. **Create the commit (commit message must follow best practices)**
   - Review the full diff carefully and draft a commit message that follows ALL of these rules:

   **Format — Conventional Commits**
   - Subject line: `<type>(<optional scope>): <subject>`
   - Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `style`, `perf`, `build`, `ci`.
   - Use a scope when it adds clarity, e.g. `feat(serializer):`, `fix(cli):`, `refactor(models):`.
   - For breaking changes, append `!` after the type/scope and add a `BREAKING CHANGE:` footer.

   **Subject line rules**
   - Imperative mood ("add", "fix", "remove" — not "added", "fixes", "removing").
   - Lowercase first letter of the subject (after the colon).
   - No trailing period.
   - Hard limit: 72 characters total. Aim for 50.

   **Body rules (include a body unless the change is genuinely trivial)**
   - Separate from subject by a blank line.
   - Wrap at ~72 characters per line.
   - Explain WHY the change was made and WHAT problem it solves — not how.

   **Process**
   - Stage only the files that belong to this change.
   - Show the proposed commit message AND the staged file list to the user.
   - Wait for explicit approval before running `git commit`.
   - When committing, pass the message via a heredoc to preserve formatting.

5. **Push the branch (confirm again before pushing)**
   - Before pushing, confirm: *"Push `<branch>` to `origin/<branch>`?"*
   - If it's a new branch, use `git push -u origin <branch>`.
   - Never force-push. Never push to `main` or `master` directly — PR flow only.

6. **Open the pull request**
   - Use `gh pr create` with a structured body.
   - PR title: short, descriptive, < 70 chars.
   - PR body sections (pass via heredoc):
     - `## Summary` — 1-3 bullets of what changed and why.
     - `## How to test` — concrete steps to verify the change works.
     - `## Risk / areas to watch` — anything reviewers should keep an eye on. Omit only if truly nothing.
   - After creating, report the PR URL back to the user.

## Safety rules

- Never skip hooks (`--no-verify`, `--no-gpg-sign`).
- Never amend existing commits unless the user explicitly asks.
- Never force-push.
- Never commit files that look like secrets (`.env`, credentials, keys).
- If anything feels off, stop and ask the user rather than guessing.

## Tone

Talk to the user like a calm release engineer: short status updates, clear checkpoints, ask before doing anything destructive. When you're done, finish with a one-line summary and the PR link.
