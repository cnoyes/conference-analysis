# Development Best Practices

This document defines mandatory development practices for Claude Code when working in this repository.

## Table of Contents
- [Planning and Architecture](#planning-and-architecture)
- [Git Workflow](#git-workflow)
- [Issue and Milestone Management](#issue-and-milestone-management)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [Documentation](#documentation)

## Planning and Architecture

### When to Use Plan Mode

**ALWAYS use plan mode** (ExitPlanMode tool) for:
- Features requiring 3+ file changes
- New features or significant enhancements
- Architectural changes or refactoring
- Changes affecting multiple components
- Anything that requires careful design decisions

**DO NOT use plan mode** for:
- Single file edits
- Bug fixes under 10 lines
- Documentation updates
- Simple dependency updates

### Plan Mode Guidelines

When in plan mode:
1. **Gather context first**: Read relevant files, understand current architecture
2. **Ask clarifying questions**: Use AskUserQuestion tool for ambiguities
3. **Present detailed plan**: Include file-by-file breakdown
4. **Identify risks**: Call out breaking changes, migration needs
5. **Get approval**: Use ExitPlanMode only after plan is complete

Example plan structure:
```markdown
## Implementation Plan

### Overview
[1-2 sentence summary]

### Changes Required

#### 1. File: path/to/file.ext
- [ ] Add function X
- [ ] Modify function Y
- [ ] Update exports

#### 2. File: path/to/other.ext
- [ ] Create new module
- [ ] Add tests

### Risks and Considerations
- Breaking change: [describe]
- Migration needed: [describe]

### Testing Strategy
- Unit tests for X
- Integration tests for Y
```

### Specialized Agents

**ALWAYS invoke specialized agents** for:

#### Software Architect Agent
- New feature design discussions
- Architectural decisions (patterns, structure)
- Technology selection
- System design reviews
- Before starting complex multi-component features

**Example invocation:**
```
I need architectural guidance on implementing feature X.
Please use the Task tool to launch a software architect agent.
```

#### Data Scientist Agent
- Statistical model design
- Algorithm selection
- Data pipeline architecture
- Performance optimization (statistical)
- Model validation strategies

#### Code Reviewer Agent
- After completing any feature (mandatory)
- Before creating pull requests
- After significant refactoring
- When changing critical paths

**DO NOT skip code review** - it's mandatory for all non-trivial changes.

## Git Workflow

### Branching Strategy

**NEVER commit directly to main** - Always use feature branches.

#### Branch Naming Convention

Format: `<type>/<issue-number>-<brief-description>`

Types:
- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `refactor/` - Code improvements without behavior changes
- `docs/` - Documentation updates
- `test/` - Test additions or modifications
- `chore/` - Maintenance tasks (deps, config)

Examples:
```bash
feature/42-add-optimization-skipping
fix/15-date-filtering-bug
refactor/33-simplify-rating-model
docs/8-update-readme-examples
```

**Issue number is required** - Create an issue first if one doesn't exist.

### Creating Feature Branches

```bash
# Always start from updated main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/42-add-optimization-skipping

# Push and set upstream
git push -u origin feature/42-add-optimization-skipping
```

### Commit Message Format

**REQUIRED format**: Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(optimization): add skip_optimization environment variable

Implement intelligent optimization skipping controlled by SKIP_OPTIMIZATION
env var. When set to 1, loads cached rankings instead of running expensive
k-swap algorithm.

Saves ~95% runtime when only predictions need updating.

Closes #42

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Mandatory elements:**
- Type prefix (feat, fix, etc.)
- Subject under 72 characters
- Body explaining what and why (not how)
- Footer with issue reference
- Claude Code attribution

### Merging Strategy

**NEVER use merge commits** - Use rebase or squash.

#### For Small Features (1-3 commits)
```bash
# Squash merge via GitHub PR
# Or locally:
git checkout main
git merge --squash feature/42-add-thing
git commit -m "feat: add thing (#42)"
git push
```

#### For Larger Features (4+ commits)
```bash
# Rebase to clean up history
git checkout feature/42-add-thing
git rebase -i main

# Then merge via PR or:
git checkout main
git merge --ff-only feature/42-add-thing
git push
```

**Delete branch after merge:**
```bash
git branch -d feature/42-add-thing
git push origin --delete feature/42-add-thing
```

### Pull Request Requirements

**Before creating PR:**
1. ✅ All tests pass
2. ✅ Code reviewer agent has reviewed changes
3. ✅ Documentation updated
4. ✅ CHANGELOG updated (if applicable)
5. ✅ No merge conflicts with main
6. ✅ Commits follow conventional format

**PR Title Format:**
```
feat: Add optimization skipping (#42)
```

**PR Description Template:**
```markdown
## Summary
[Brief description of changes]

## Changes
- Added X
- Modified Y
- Removed Z

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Related Issues
Closes #42

## Breaking Changes
[List any breaking changes or write "None"]

## Screenshots (if applicable)
[Add screenshots for UI changes]
```

## Issue and Milestone Management

### Creating Issues

**ALWAYS create an issue before starting work** on non-trivial changes.

**Issue Title Format:**
```
[TYPE] Brief description (under 72 chars)
```

Types: `[FEATURE]`, `[BUG]`, `[REFACTOR]`, `[DOCS]`, `[CHORE]`

**Issue Template:**
```markdown
## Description
[Clear description of the issue/feature]

## Motivation
[Why is this needed?]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests added
- [ ] Documentation updated

## Additional Context
[Any relevant context, screenshots, or links]

## Related Issues
[Link to related issues if any]
```

**Labels** (create these in your repo):
- `priority: high`, `priority: medium`, `priority: low`
- `type: feature`, `type: bug`, `type: refactor`, `type: docs`
- `status: planning`, `status: in-progress`, `status: blocked`, `status: review`
- `size: small` (<1 day), `size: medium` (1-3 days), `size: large` (3+ days)

### Creating Milestones

**Use milestones** for organizing related issues into releases or sprints.

**Milestone naming:**
```
v1.2.0 - Optimization Improvements
Sprint 2024-W43
Q4 2024 Goals
```

**Milestone description:**
```markdown
## Goals
- Goal 1
- Goal 2

## Target Date
2024-11-01

## Success Criteria
- [ ] All issues completed
- [ ] Tests passing
- [ ] Documentation updated
```

### Issue Workflow

```
1. Create issue with template
2. Add labels (type, priority, size)
3. Assign to milestone (if applicable)
4. Create feature branch: feature/<issue-number>-description
5. Work on implementation
6. Create PR referencing issue
7. Code review
8. Merge and close issue
```

## Code Quality

### Pre-Commit Checklist

Before any commit, verify:
- [ ] Code follows project style guide
- [ ] No commented-out code (remove or explain)
- [ ] No debug print statements
- [ ] No hardcoded values (use config/env vars)
- [ ] Descriptive variable/function names
- [ ] Functions under 50 lines (guideline, not rule)
- [ ] Files under 500 lines (consider splitting)

### Code Review Checklist

**MANDATORY before PR:**
- [ ] Invoke code-reviewer agent
- [ ] Address all findings
- [ ] No security vulnerabilities
- [ ] No performance regressions
- [ ] Error handling present
- [ ] Edge cases handled

### R-Specific Quality Standards

For R projects:
- [ ] Use `tidyverse` style guide
- [ ] Document functions with roxygen2 comments
- [ ] Type hints in function signatures when possible
- [ ] Suppress package messages appropriately
- [ ] Use meaningful variable names (no `x`, `df` unless in pipelines)
- [ ] Keep pipelines readable (one operation per line)
- [ ] Handle NA values explicitly

Example:
```r
#' Calculate team ratings
#'
#' @param game_df Data frame with game results
#' @param train_date Date for training cutoff
#' @return Data frame with team ratings
create_rating_df <- function(game_df, train_date) {
  # Implementation
}
```

## Testing

### Test Coverage Requirements

**REQUIRED coverage:**
- New features: 80% minimum
- Bug fixes: Must include regression test
- Refactoring: Maintain existing coverage

### Test Organization

```
tests/
  testthat/
    test-01-data-loading.R
    test-06-rating-model.R
    test-08-optimization.R
```

**Test naming:**
```r
test_that("create_rating_df returns correct structure", {
  # Arrange
  game_df <- create_test_game_data()

  # Act
  result <- create_rating_df(game_df, Sys.Date())

  # Assert
  expect_s3_class(result, "data.frame")
  expect_true("Rating" %in% colnames(result))
})
```

### When to Write Tests

**ALWAYS write tests for:**
- New functions (before implementation - TDD)
- Bug fixes (regression tests)
- Critical business logic
- Data transformations
- API endpoints

**Tests are optional for:**
- Simple getters/setters
- Obvious wrappers
- UI-only code

## Documentation

### README.md Requirements

**MUST include:**
- [ ] Project description (1 paragraph)
- [ ] Prerequisites/dependencies
- [ ] Installation instructions
- [ ] Usage examples
- [ ] Configuration options
- [ ] Contributing guidelines
- [ ] License

### CLAUDE.md Requirements

**MUST include:**
- [ ] Project overview for AI assistants
- [ ] Key commands with examples
- [ ] Architecture overview
- [ ] Important configuration
- [ ] Data flow diagrams (if applicable)
- [ ] Common patterns and conventions

### Code Comments

**DO write comments for:**
- Complex algorithms (explain why, not what)
- Non-obvious optimizations
- Workarounds for bugs/limitations
- Business logic decisions

**DON'T write comments for:**
- Self-explanatory code
- Restating what code does
- Commented-out code (delete it)

**Examples:**

✅ Good:
```r
# Use 3.5 year decay to balance recency vs historical data
# Shorter window (2 years) overfit to recent anomalies
weight <- max(1 - (days_ago / 365 / 3.5), 0)
```

❌ Bad:
```r
# Calculate weight
weight <- max(1 - (days_ago / 365 / 3.5), 0)
```

### Changelog

**REQUIRED for user-facing changes:**

Format:
```markdown
# Changelog

## [Unreleased]
### Added
- Feature X with optimization skipping

### Changed
- Improved performance of Y

### Deprecated
- Function Z (use W instead)

### Removed
- Old playoff CSV loading

### Fixed
- Date filtering for 10/04/2025 games

## [1.0.0] - 2024-10-22
...
```

## Enforcement

Claude Code will:
1. **Refuse to proceed** if mandatory steps are skipped
2. **Remind you** of best practices before committing
3. **Invoke agents** automatically when appropriate
4. **Create issues** when requested or when finding bugs

If you want to skip a practice:
- Explicitly state why
- Document the exception
- Get approval for deviations from required practices

---

**Remember**: These practices exist to maintain code quality, enable collaboration, and prevent bugs. Following them saves time in the long run.
