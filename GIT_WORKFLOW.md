# Git Workflow for Constitutional AI

This guide is designed to help you manage your code safely and effectively, even if you feel "bad at git".

## 1. The Golden Rule
**Never commit directly to `main` (or `master`).**
Always work in a separate branch. This keeps your working code safe from breaking changes.

## 2. Starting a New Task

Before you start writing code, create a new branch.

```bash
# 1. Make sure you are on the main branch and it's up to date
git checkout main
git pull

# 2. Create a new branch with a descriptive name
# Format: <type>/<description>
# Types: feat (feature), fix (bugfix), docs (documentation), chore (cleanup)

git checkout -b feat/add-new-scraper
# OR
git checkout -b fix/dashboard-layout
```

## 3. Saving Your Work

As you work, save your progress often.

```bash
# 1. See what files you have changed
git status

# 2. Add the files you want to save
git add .
# (Using . adds everything. To be safer, add specific files: git add filename.py)

# 3. Commit your changes with a message describing WHAT you did
git commit -m "feat: add basic scraper structure"
```

## 4. Uploading Your Work

When you are ready to share your code or merge it.

```bash
# Push your branch to GitHub
git push origin <your-branch-name>

# Example:
git push origin feat/add-new-scraper
```

## 5. Merging Code (Pull Request)

1. Go to GitHub in your browser.
2. You should see a yellow banner saying "Compare & pull request". Click it.
3. Review your changes.
4. Click "Create Pull Request".
5. Once approved (or if you are working alone, once you are happy), click "Merge pull request".

## 6. Cleaning Up

After your code is merged into main:

```bash
# 1. Switch back to main
git checkout main

# 2. Download the new changes (including your merged code)
git pull

# 3. Delete your old branch (optional but keeps things clean)
git branch -d feat/add-new-scraper
```

## Cheat Sheet

| Command | What it does |
|---------|--------------|
| `git status` | Shows which files have changed. Run this constantly! |
| `git checkout -b <name>` | Creates and switches to a new branch. |
| `git checkout <name>` | Switches to an existing branch. |
| `git add .` | Stages all changes for the next commit. |
| `git commit -m "msg"` | Saves the staged changes permanently in history. |
| `git push` | Uploads your commits to the server. |
| `git pull` | Downloads new commits from the server. |

## Troubleshooting

**"I messed up and don't know where I am!"**
Run `git status` to see where you are.

**"I want to undo my changes to a file!"**
`git checkout -- <filename>` (WARNING: This deletes your unsaved work in that file)

**"I want to see what I changed!"**
`git diff`
