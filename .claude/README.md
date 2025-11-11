# .claude Directory

This directory contains development guidelines and templates for maintaining consistent best practices across repositories.

## Files in This Directory

### 📋 BEST_PRACTICES.md
**Comprehensive development guide** covering:
- When to use plan mode and specialized agents
- Git branching and merging strategies
- Commit message conventions
- Issue and milestone management
- Code quality standards
- Testing requirements
- Documentation guidelines

**Target audience**: Claude Code AI assistant and developers
**When to read**: Before starting any significant development work

### 🚀 QUICK_REFERENCE.md
**One-page cheat sheet** for common tasks:
- Starting new work
- Common commands
- Commit message format
- Creating PRs
- Using Claude Code agents
- Troubleshooting

**Target audience**: Developers who need quick answers
**When to read**: Daily reference while working

### 📝 CLAUDE_TEMPLATE.md
**Template for CLAUDE.md files** in new repositories.

**Usage**:
1. Copy to new repo as `CLAUDE.md`
2. Customize Project Overview section
3. Update Key Commands section
4. Fill in Architecture section

**Target audience**: Setting up new repositories
**When to use**: Creating a new project

### 🔧 setup-best-practices.sh
**Script to copy all best practices files** to a new repository.

**Usage**:
```bash
# From the new repository:
cd /path/to/new/repo
bash /path/to/ute-conference-rankings/.claude/setup-best-practices.sh
```

**What it copies**:
- `.claude/BEST_PRACTICES.md`
- `.claude/QUICK_REFERENCE.md`
- `.claude/CLAUDE_TEMPLATE.md` → `CLAUDE.md` (if doesn't exist)
- `.github/ISSUE_TEMPLATE/*.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CONTRIBUTING.md` (if doesn't exist)
- `.gitignore` (if doesn't exist)

**Target audience**: Repository administrators
**When to use**: Setting up a new project

## How These Files Work Together

```
┌─────────────────────────────────────────────────────────┐
│                    New Developer                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
            ┌─────────────────────────────┐
            │  CONTRIBUTING.md (overview)  │
            └─────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  CLAUDE.md   │  │QUICK_REFERENCE│  │BEST_PRACTICES│
│ (AI context) │  │  (1-pager)   │  │ (detailed)   │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                ┌──────────────────┐
                │  GitHub Templates │
                │  (issues/PRs)    │
                └──────────────────┘
                          ▼
                    Development
```

## Using These Files

### For New Contributors
1. Start with `CONTRIBUTING.md` (in repo root)
2. Read `CLAUDE.md` (in repo root)
3. Keep `QUICK_REFERENCE.md` handy
4. Refer to `BEST_PRACTICES.md` for detailed guidance

### For Claude Code AI
Claude Code automatically reads:
1. `CLAUDE.md` (project-specific instructions)
2. `BEST_PRACTICES.md` (comprehensive guidelines)

Claude Code will:
- Enforce branching strategy
- Require issues before features
- Suggest plan mode for complex tasks
- Invoke code-reviewer agent before PRs
- Follow conventional commit format

### For Repository Administrators

**Setting up a new repository:**
```bash
cd /path/to/new/repo
bash /path/to/ute-conference-rankings/.claude/setup-best-practices.sh
```

**Then customize:**
1. Edit `CLAUDE.md` - add project-specific details
2. Review `CONTRIBUTING.md` - adjust for your project
3. Create GitHub labels (see BEST_PRACTICES.md)
4. Update `README.md` - link to CONTRIBUTING.md

**Updating existing repositories:**
1. Copy updated `BEST_PRACTICES.md` from this repo
2. Review changes in `QUICK_REFERENCE.md`
3. Update `CLAUDE.md` if workflow changed

## Enforcing Best Practices

### Automatic Enforcement (Claude Code)
When working with Claude Code, these practices are **automatically enforced**:
- ✅ Feature branches required
- ✅ Issues required for features
- ✅ Plan mode for complex changes
- ✅ Code review before PRs
- ✅ Conventional commits
- ✅ Documentation updates

### Manual Enforcement (Humans)
For human developers:
- Issue templates guide proper reporting
- PR template ensures checklist completion
- CONTRIBUTING.md explains expectations
- Code review verifies compliance

### Optional CI/CD Enforcement
Consider adding:
- Commit message linting (commitlint)
- Branch name validation
- Automated code review (GitHub Actions)
- Test coverage requirements
- Documentation link checking

## Customization

### For R Projects
Current templates are optimized for R. For other languages:

**Python projects**: Update test examples to pytest format
**JavaScript/TypeScript**: Update to Jest/Vitest examples
**Go**: Update to go test examples

### For Different Team Sizes

**Solo projects**: Can relax PR requirements
**Small teams (2-5)**: Use as-is
**Large teams (5+)**: Add code owner requirements

### For Different Workflows

**Research projects**: Add experiment tracking
**Data science**: Add model versioning
**Web apps**: Add deployment checklists

## Maintenance

### Keeping Templates Updated

When improving these templates:
1. Update in one "source" repository (this one)
2. Document changes in this README
3. Copy to other repositories as needed

### Version History

- **2024-10-22**: Initial creation
  - Created comprehensive BEST_PRACTICES.md
  - Created QUICK_REFERENCE.md
  - Created CLAUDE_TEMPLATE.md
  - Created setup script
  - Created GitHub issue/PR templates

## Questions?

- Read the files - they're comprehensive
- Check examples in the files
- Open a discussion on GitHub
- Review recent PRs for patterns

## Related Files

In repository root:
- `CLAUDE.md` - AI assistant instructions (customized from template)
- `CONTRIBUTING.md` - Human contributor guide
- `README.md` - Project overview

In `.github/`:
- `ISSUE_TEMPLATE/` - Issue templates
- `PULL_REQUEST_TEMPLATE.md` - PR template
