# Quick Reference Guide

One-page reference for common development tasks.

## Starting New Work

```bash
# 1. Create issue on GitHub first
# 2. Create branch
git checkout main && git pull
git checkout -b feature/42-brief-description

# 3. Start development
# (Write tests first!)
```

## Common Commands

### Running Tests
```bash
Rscript -e "devtools::test()"
# or
R CMD check
```

### Running Pipeline
```bash
# Full optimization
Rscript run_ranking.R

# Skip optimization (fast)
SKIP_OPTIMIZATION=1 Rscript run_ranking.R
```

### Updating Dependencies
```bash
R -e "renv::restore()"  # Install
R -e "renv::snapshot()" # Update lockfile
```

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

Closes #<issue-number>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Branch Naming

Format: `<type>/<issue-number>-<description>`

Examples:
- `feature/42-add-caching`
- `fix/15-date-bug`
- `docs/8-update-readme`

## Creating Pull Request

```bash
# Before PR:
# ✅ Tests pass
# ✅ Code reviewed (use code-reviewer agent)
# ✅ Docs updated
# ✅ No conflicts

git push -u origin feature/42-brief-description
# Then create PR on GitHub
```

## Using Claude Code

### Plan Mode (for complex features)
1. Ask Claude to enter plan mode
2. Review the plan
3. Approve to start implementation

### Code Review (mandatory before PR)
```
Please invoke the code-reviewer agent to review my changes.
```

### Specialized Agents

**Software Architect**: For design decisions
```
Please use the Task tool to launch a software architect agent
to help design the caching layer.
```

**Data Scientist**: For statistical/ML work
```
Please use the Task tool to launch a data scientist agent
to review the rating algorithm.
```

## Checklist Before Merging

- [ ] Issue number in PR title: `feat: Add feature (#42)`
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Conventional commits
- [ ] No conflicts with main

## Common Patterns

### R Function Template
```r
#' Brief description
#'
#' @param param1 Description
#' @param param2 Description
#' @return Description
#' @export
function_name <- function(param1, param2) {
  # Implementation
}
```

### R Test Template
```r
test_that("function does X when Y", {
  # Arrange
  input <- create_test_data()

  # Act
  result <- function_name(input)

  # Assert
  expect_equal(result, expected)
})
```

## Issue Labels

- **Type**: `type: feature`, `type: bug`, `type: refactor`, `type: docs`
- **Priority**: `priority: high`, `priority: medium`, `priority: low`
- **Status**: `status: planning`, `status: in-progress`, `status: review`, `status: blocked`
- **Size**: `size: small`, `size: medium`, `size: large`

## When to Use What

| Task | Tool/Approach |
|------|---------------|
| Simple bug fix (<10 lines) | Direct commit to branch |
| Feature (3+ files) | Plan mode → feature branch |
| Architectural decision | Software architect agent |
| Algorithm design | Data scientist agent |
| Before PR | Code reviewer agent |
| Complex refactoring | Plan mode + code review |

## Git Workflow

```
main
  ├─ feature/42-add-thing
  │   └─ (squash merge) → main
  │
  ├─ fix/15-fix-bug
  │   └─ (squash merge) → main
  │
  └─ feature/50-big-refactor
      └─ (rebase merge) → main
```

## Files to Update

When adding a feature, typically update:
- [ ] Source code (`R/`, `src/`, etc.)
- [ ] Tests (`tests/`)
- [ ] Documentation (`README.md`, function docs)
- [ ] CLAUDE.md (if workflow changes)
- [ ] CHANGELOG.md (user-facing changes)

## Getting Unstuck

1. **Read the docs**: Check README, CLAUDE.md, BEST_PRACTICES.md
2. **Check issues**: Search existing issues
3. **Ask for help**: Create discussion or issue
4. **Use agents**: Invoke specialized agents for complex problems

## Resources

- [BEST_PRACTICES.md](.claude/BEST_PRACTICES.md) - Comprehensive guide
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution workflow
- [CLAUDE.md](../CLAUDE.md) - Project-specific guidelines
- [Issue Templates](../.github/ISSUE_TEMPLATE/) - Creating issues
- [PR Template](../.github/PULL_REQUEST_TEMPLATE.md) - Creating PRs
