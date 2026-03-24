# Contributing to Carbon Optimizer

Thank you for contributing! Please follow these guidelines to keep the project clean and consistent.

---

## Branch Naming

```
feature/section-<N>-<short-name>    # Section work
fix/<short-description>             # Bug fixes
docs/<short-description>            # Documentation only
```

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scope): short description      # New feature
fix(scope): short description       # Bug fix
docs(scope): short description      # Docs change
test(scope): short description      # Tests only
chore(scope): short description     # Tooling/config
ops(scope): short description       # Infra/scripts
```

**Scopes:** `iam`, `lambda`, `dynamodb`, `sns`, `eventbridge`, `s3`, `ssm`, `cur`, `cloudformation`

## Pull Request Process

1. PR title must match: `Section N: <Title>` or `Fix: <description>`
2. All verification outputs must be pasted in the PR description
3. At least 1 approval required before merging
4. Use **Squash and merge** to keep main history clean
5. Link related issues with `Closes #<number>`

## What NOT to Commit

- AWS credentials or account IDs
- `lambda-function.zip` (gitignored — built at deploy time)
- `/tmp/` files or local test artifacts
- Real email addresses

## Environment Variables

Never hardcode environment variable values in scripts. Always use shell variables. The `.gitignore` excludes `.env` files.

## Code Style (Python)

- Follow PEP 8
- Use `logging` instead of `print` in Lambda functions
- Handle all exceptions explicitly and log them
