# Git & GitHub Integration Guide

Complete guide to using Git and GitHub features in Mini Assistant.

## Features

✅ **Initialize Repository** - Create new Git repo in /app directory
✅ **Stage Files** - Add files to staging area
✅ **Commit Changes** - Commit with custom messages
✅ **Add Remote** - Connect to GitHub repositories
✅ **Push to GitHub** - Upload your code to GitHub
✅ **Pull from GitHub** - Download latest changes
✅ **Branch Status** - View current branch and file status
✅ **Activity Log** - Track all Git operations

## Quick Start

### 1. Initialize Git Repository

If starting fresh:
1. Go to **GIT & GITHUB** tab
2. Click **INITIALIZE GIT** button
3. Your /app directory is now a Git repository!

### 2. Connect to GitHub

#### Create a new repository on GitHub:
1. Go to https://github.com/new
2. Create a new repository (e.g., "my-mini-assistant-project")
3. Copy the repository URL: `https://github.com/yourusername/repo-name.git`

#### Add remote in Mini Assistant:
1. In **GIT & GITHUB** tab
2. Remote name: `origin` (default)
3. Paste your GitHub URL
4. Click **ADD REMOTE**

### 3. Commit Your Code

1. Write a commit message (e.g., "Initial commit" or "Added new features")
2. Click **STAGE ALL** to stage all changes
3. Click **COMMIT** to commit staged files

### 4. Push to GitHub

**IMPORTANT:** First time push requires authentication:

#### Option A: Using GitHub Token (Recommended)
1. Create Personal Access Token on GitHub:
   - Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click "Generate new token"
   - Select scopes: `repo` (all)
   - Copy the token

2. Configure Git with token:
   ```bash
   # In Terminal tab, run:
   git config --global credential.helper store
   ```

3. First push will ask for credentials:
   - Username: your GitHub username
   - Password: paste your personal access token

4. Click **PUSH** button

#### Option B: SSH Key (Advanced)
1. Generate SSH key
2. Add to GitHub account
3. Use SSH URL instead of HTTPS

### 5. Pull Latest Changes

To get updates from GitHub:
1. Click **PULL** button
2. Latest changes will be downloaded

## Common Workflows

### Workflow 1: New Project → GitHub

```
1. Build your app in Mini Assistant
2. Click "GIT & GITHUB" tab
3. Click "INITIALIZE GIT"
4. Add GitHub remote
5. Stage All → Commit → Push
6. Your code is now on GitHub! 🎉
```

### Workflow 2: Regular Updates

```
1. Make changes to your code
2. Go to "GIT & GITHUB" tab
3. Write commit message
4. Stage All → Commit
5. Push to GitHub
```

### Workflow 3: Pull Team Changes

```
1. Team member pushed changes
2. Go to "GIT & GITHUB" tab
3. Click PULL
4. Your local code is updated
```

## Status Indicators

**Branch Information:**
- Shows current branch (usually `main` or `master`)
- Updates in real-time

**Modified Files:**
- Yellow indicator: Files changed but not staged
- Shows count of modified files

**Staged Files:**
- Green indicator: Files ready to commit
- Shows count of staged files

## Git Commands Behind the Scenes

Mini Assistant runs these commands for you:

| Action | Git Command |
|--------|-------------|
| Initialize | `git init` |
| Stage All | `git add .` |
| Commit | `git commit -m "message"` |
| Push | `git push origin main` |
| Pull | `git pull origin main` |
| Add Remote | `git remote add origin URL` |

## Troubleshooting

### "Push failed"
**Cause:** No authentication or wrong credentials
**Fix:** 
1. Create GitHub Personal Access Token
2. Use token as password when prompted
3. Or configure SSH keys

### "Permission denied"
**Cause:** No write access to repository
**Fix:**
1. Make sure you own the repository
2. Or ask owner to add you as collaborator
3. Check token permissions include `repo` scope

### "Nothing to commit"
**Cause:** No changes to commit
**Fix:**
1. Make some changes to files first
2. Or use Files/Code Review tabs to edit code

### "Remote already exists"
**Cause:** Remote name already configured
**Fix:**
1. Mini Assistant automatically updates it
2. Or use different remote name

### "Not a git repository"
**Cause:** Git not initialized
**Fix:**
1. Click "INITIALIZE GIT" button first

## Best Practices

### Commit Messages
✅ **Good:**
- "Add user authentication feature"
- "Fix: Memory leak in chat component"
- "Update: Improve voice recognition accuracy"

❌ **Bad:**
- "update"
- "fix"
- "changes"

### Commit Frequency
- Commit after completing a feature
- Commit before making major changes
- Commit at end of work session

### What to Commit
✅ **Include:**
- Source code files
- Configuration files
- Documentation
- README files

❌ **Exclude:**
- `node_modules/` (dependencies)
- `.env` files (secrets)
- Build outputs
- Temporary files

## Advanced Usage

### Multiple Branches
Create feature branches:
1. In Terminal: `git checkout -b feature-name`
2. Make changes
3. Commit and push: `git push origin feature-name`

### Collaborate with Team
1. Team member clones your repo
2. They make changes and push
3. You click PULL to get updates
4. Conflicts? Resolve in Files tab

### Connect Multiple Remotes
Add additional remotes (e.g., staging, production):
1. Remote name: `staging`
2. URL: your staging repo URL
3. Push to specific remote: Select from dropdown

## Integration with Other Features

### With App Builder
1. Generate app with App Builder
2. Files are created in /app
3. Go to Git tab
4. Commit and push to GitHub

### With Code Review
1. Review and fix code
2. Apply fixes
3. Go to Git tab
4. Commit improved code

### With File Manager
1. Edit files manually
2. Save changes
3. Go to Git tab
4. Commit updates

## Security Notes

⚠️ **Never commit:**
- API keys
- Passwords
- Personal access tokens
- Database credentials
- `.env` files with secrets

✅ **Always:**
- Use `.gitignore` to exclude sensitive files
- Use environment variables
- Review changes before committing

## GitHub Features

Once pushed, you can use GitHub for:
- Code reviews
- Issues tracking
- Pull requests
- GitHub Actions (CI/CD)
- Collaborator access
- Version history
- Code search

## Example: Full Workflow

```
1. Create "My Todo App" with App Builder
   → Files created in /app

2. Go to GIT & GITHUB tab
   → Click "INITIALIZE GIT"
   → Status shows: Branch: main, Modified: 5 file(s)

3. Add GitHub remote
   → Remote name: origin
   → URL: https://github.com/myusername/my-todo-app.git
   → Click "ADD REMOTE"
   → Log shows: "Added remote: origin"

4. Commit changes
   → Commit message: "Initial commit - Todo app with authentication"
   → Click "STAGE ALL"
   → Click "COMMIT"
   → Log shows: "Committed: Initial commit..."

5. Push to GitHub
   → Click "PUSH"
   → Enter GitHub credentials if first time
   → Log shows: "Pushed to origin/main"
   → Done! ✅

6. View on GitHub
   → Open https://github.com/myusername/my-todo-app
   → Your code is live!
```

## Next Steps

After mastering Git integration:
1. Set up GitHub Actions for auto-deployment
2. Use GitHub Pages for hosting
3. Enable branch protection rules
4. Set up webhooks for notifications
5. Integrate with CI/CD pipelines

---

**Need Help?** Check the Git Activity Log on the right panel to see what commands were executed and any error messages.
