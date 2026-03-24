# GitHub Project Setup Guide

Complete step-by-step instructions for setting up the GitHub repository and project board for the Carbon Optimizer project.

---

## Step 1 — Create the GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Fill in the details:
   - **Repository name:** `carbon-optimizer`
   - **Description:** `Automated AWS carbon footprint optimization using Cost Explorer, Lambda, EventBridge, and DynamoDB`
   - **Visibility:** Private (recommended for AWS projects with IAM details)
   - ✅ **Add a README file** — uncheck this (we have our own)
   - **.gitignore:** Select `Python`
   - **License:** MIT (or your preference)
3. Click **Create repository**

---

## Step 2 — Initialize and Push Local Repository

```bash
# In your local project directory
cd carbon-optimizer

git init
git add .
git commit -m "# Build artifacts
lambda-function.zip
*.zip

# Local environment files
.env
.env.*
*.local

# Temp files
/tmp/
*.tmp

# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# AWS CLI artifacts
aws-exports.json

# macOS
.DS_Store

# IDE
.vscode/
.idea/
*.swp

# JSON policy files generated at runtime (contain env vars)
lambda-trust-policy.json
lambda-permissions-policy.json
cur-definition.json
"

git remote add origin https://github.com/<your-org>/carbon-optimizer.git
git branch -M main
git push -u origin main
```

---

## Step 3 — Set Up Branch Protection Rules

Go to **Settings → Branches → Add branch protection rule**:

- **Branch name pattern:** `main`
- ✅ Require a pull request before merging
- ✅ Require approvals: **1**
- ✅ Require status checks to pass before merging
- ✅ Require branches to be up to date before merging
- ✅ Do not allow bypassing the above settings

Click **Create**.

---

## Step 4 — Create Labels

Go to **Issues → Labels** and create these labels (delete defaults if you like):

| Label Name | Color | Description |
|------------|-------|-------------|
| `infrastructure` | `#0075ca` | IAM, S3, DynamoDB setup |
| `backend` | `#e4e669` | Lambda function code |
| `automation` | `#d93f0b` | EventBridge, SNS |
| `configuration` | `#0e8a16` | SSM, CUR, CloudFormation |
| `testing` | `#cc317c` | Validation and cleanup |
| `bug` | `#ee0701` | Something isn't working |
| `documentation` | `#bfd4f2` | Improvements to docs |

---

## Step 5 — Create Milestones

Go to **Issues → Milestones → New milestone**:

| Milestone | Due Date | Description |
|-----------|----------|-------------|
| `Phase 1: Foundation` | Day 1–2 | IAM, DynamoDB, S3 setup |
| `Phase 2: Core Logic` | Day 2–3 | Lambda function deployed |
| `Phase 3: Automation` | Day 3–4 | SNS, EventBridge, CUR, SSM |
| `Phase 4: Validation` | Day 4–5 | Testing complete, cleanup ready |

---

## Step 6 — Create Issues for Each Task

Create one issue per task (use the table below as a guide). For each issue:

- Set the appropriate **label** and **milestone**
- Assign to the team member responsible for that section

### Section 1 Issues

| Title | Label | Milestone | Assignee |
|-------|-------|-----------|----------|
| Create encrypted S3 bucket | `infrastructure` | Phase 1 | Member 1 |
| Create IAM trust and permissions policy files | `infrastructure` | Phase 1 | Member 1 |
| Provision Lambda execution IAM role | `infrastructure` | Phase 1 | Member 1 |
| Create DynamoDB metrics table | `infrastructure` | Phase 1 | Member 1 |
| Add GSI for service-level carbon queries | `infrastructure` | Phase 1 | Member 1 |

### Section 2 Issues

| Title | Label | Milestone | Assignee |
|-------|-------|-----------|----------|
| Implement Lambda handler and Cost Explorer integration | `backend` | Phase 2 | Member 2 |
| Implement carbon analysis logic with emission factors | `backend` | Phase 2 | Member 2 |
| Implement DynamoDB storage and SNS notification functions | `backend` | Phase 2 | Member 2 |
| Package and deploy Lambda function | `backend` | Phase 2 | Member 2 |

### Section 3 Issues

| Title | Label | Milestone | Assignee |
|-------|-------|-----------|----------|
| Create SNS notifications topic | `automation` | Phase 3 | Member 3 |
| Configure email subscription | `automation` | Phase 3 | Member 3 |
| Create EventBridge scheduler role | `automation` | Phase 3 | Member 3 |
| Create monthly and weekly EventBridge schedules | `automation` | Phase 3 | Member 3 |

### Section 4 Issues

| Title | Label | Milestone | Assignee |
|-------|-------|-----------|----------|
| Configure S3 bucket policy for CUR delivery | `configuration` | Phase 3 | Member 4 |
| Create Cost and Usage Report definition | `configuration` | Phase 3 | Member 4 |
| Create SSM sustainability configuration parameter | `configuration` | Phase 3 | Member 4 |
| Create and validate CloudFormation sustainable infrastructure template | `configuration` | Phase 3 | Member 4 |

### Section 5 Issues

| Title | Label | Milestone | Assignee |
|-------|-------|-----------|----------|
| Write full resource validation script | `testing` | Phase 4 | Member 5 |
| End-to-end Lambda invocation test | `testing` | Phase 4 | Member 5 |
| DynamoDB data write verification | `testing` | Phase 4 | Member 5 |
| Write complete cleanup script | `testing` | Phase 4 | Member 5 |

---

## Step 7 — Create GitHub Project Board

1. Go to your GitHub profile or org → **Projects → New project**
2. Select **Board** layout
3. Name it: `Carbon Optimizer Sprint Board`
4. Create these columns:

| Column | Description |
|--------|-------------|
| 📋 Backlog | All issues created but not started |
| 🔨 In Progress | Actively being worked on |
| 👀 In Review | PR open, awaiting review |
| ✅ Done | Merged to main |

5. Add all issues to the **Backlog** column
6. Link the project to your repository: **Project settings → Linked repositories → Add repository**

---

## Step 8 — Create Feature Branches

Each team member creates their branch from `main`:

```bash
# Member 1
git checkout main && git pull
git checkout -b feature/section-1-iam-dynamodb
git push -u origin feature/section-1-iam-dynamodb

# Member 2
git checkout main && git pull
git checkout -b feature/section-2-lambda

# Member 3
git checkout main && git pull
git checkout -b feature/section-3-sns-eventbridge

# Member 4
git checkout main && git pull
git checkout -b feature/section-4-cur-ssm

# Member 5
git checkout main && git pull
git checkout -b feature/section-5-testing-cleanup
```

---

## Step 9 — Pull Request Workflow

Each member follows this process when their section is complete:

1. **Commit all changes** with descriptive commit messages (see section files for exact messages)
2. **Push branch:** `git push origin feature/section-X-<name>`
3. **Open PR** on GitHub:
   - Base: `main`
   - Title: `Section X: <Section Name>`
   - Description: paste verification outputs from your section
   - Link related issues with `Closes #<issue-number>`
   - Assign **Team Member 5** as reviewer (+ section author as assignee)
4. **Team Member 5 reviews** and approves or requests changes
5. **Merge** using "Squash and merge" to keep `main` history clean

### Merge Order

Sections must be merged in dependency order:

```
Section 1  →  Section 2  →  Section 3
                         →  Section 4  →  Section 5
```

Sections 3 and 4 can be merged in parallel after Section 2.

---

## Step 10 — GitHub Actions CI (Optional)

A basic validation workflow is included at `.github/workflows/validate.yml`. It runs on every PR to `main` and checks:

- Python syntax validation on `lambda-function/index.py`
- CloudFormation template linting (if `cfn-lint` is available)
- Shell script syntax checking

To activate: push the `.github/` directory to `main` and the workflow will trigger automatically on the next PR.

---

## Quick Reference: Git Commands

```bash
# Daily workflow
git status                          # Check what's changed
git add <file>                      # Stage specific file
git add .                           # Stage all changes
git commit -m "feat: description"   # Commit with message
git push                            # Push to remote branch
git pull origin main                # Pull latest main changes

# Sync your branch with main
git fetch origin
git rebase origin/main

# Check branch status
git log --oneline -10
git diff main
```

## Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

Types: feat, fix, docs, test, build, chore, ops
Scope: iam, lambda, dynamodb, sns, eventbridge, s3, ssm, cur, cloudformation

Examples:
feat(lambda): add carbon analysis function
fix(iam): correct s3 bucket ARN in policy
docs(readme): update architecture diagram
test(dynamodb): add data validation check
ops(cleanup): add s3 bucket deletion to cleanup script
```
