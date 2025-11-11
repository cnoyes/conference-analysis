# Contributing Guide

Thank you for contributing to this project! This guide will help you get started.

## Quick Start

1. **Read the documentation**
   - `README.md` - Project overview and usage
   - `CLAUDE.md` - Development guidelines for AI assistants
   - `.claude/BEST_PRACTICES.md` - Comprehensive best practices

2. **Set up your environment**
   ```bash
   # Clone the repository
   git clone https://github.com/cnoyes/ute-conference-rankings.git
   cd ute-conference-rankings

   # Install dependencies
   R -e "renv::restore()"
   ```

3. **Create an issue**
   - Use issue templates: [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) or [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md)
   - Describe what you want to work on
   - Wait for approval before starting work

4. **Create a feature branch**
   ```bash
   git checkout -b feature/42-your-feature
   ```

5. **Make your changes**
   - Write tests first (TDD)
   - Follow code style guidelines
   - Keep commits atomic and well-described

6. **Submit a pull request**
   - Follow the [PR template](.github/PULL_REQUEST_TEMPLATE.md)
   - Reference the related issue
   - Wait for review

## Development Workflow

### 1. Before You Start

- [ ] Issue exists for your work
- [ ] Issue is approved/assigned
- [ ] You understand the requirements
- [ ] You've read relevant documentation

### 2. Creating a Branch

**Branch naming format**: `<type>/<issue-number>-<brief-description>`

Types:
- `feature/` - New features
- `fix/` - Bug fixes
- `refactor/` - Code improvements
- `docs/` - Documentation
- `test/` - Tests
- `chore/` - Maintenance

Examples:
```bash
git checkout -b feature/42-add-caching
git checkout -b fix/15-date-parsing-error
git checkout -b docs/8-update-api-docs
```

### 3. Writing Code

**Follow these principles:**
- Test-Driven Development (write tests first)
- Single Responsibility (one change per commit)
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple)
- Self-documenting code (clear names)

**For R code:**
- Follow [tidyverse style guide](https://style.tidyverse.org/)
- Use roxygen2 for function documentation
- Suppress package messages appropriately
- Handle NA values explicitly

### 4. Writing Tests

**Required coverage: 80% for new code**

Test file naming:
```
tests/testthat/test-<component>.R
```

Test naming:
```r
test_that("function_name does what when condition", {
  # Arrange
  input <- create_test_input()

  # Act
  result <- function_name(input)

  # Assert
  expect_equal(result, expected_value)
})
```

### 5. Committing Changes

**Commit message format** (required):
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Formatting
- `refactor` - Code restructuring
- `test` - Tests
- `chore` - Maintenance

**Example:**
```
feat(optimization): add intelligent skipping via env var

Implement SKIP_OPTIMIZATION environment variable to skip expensive
k-swap optimization when only predictions need updating.

- Read env var in run_ranking.R
- Load cached rankings when SKIP_OPTIMIZATION=1
- Run full optimization when SKIP_OPTIMIZATION=0
- Add fallback to full optimization if no cache exists

Closes #42

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Commit checklist:**
- [ ] Follows conventional format
- [ ] Subject under 72 characters
- [ ] Body explains what and why (not how)
- [ ] References issue number
- [ ] Includes co-author tag if using AI

### 6. Creating Pull Requests

**Before creating PR:**
- [ ] All tests pass locally
- [ ] Code reviewed by code-reviewer agent (if using Claude Code)
- [ ] Documentation updated
- [ ] No merge conflicts with main
- [ ] Commits follow conventional format

**PR title format:**
```
feat: Add intelligent optimization skipping (#42)
```

**Use the PR template** - it will auto-populate when you create a PR.

### 7. Code Review Process

Your PR will be reviewed for:
- **Correctness**: Does it work as intended?
- **Tests**: Are there adequate tests?
- **Style**: Does it follow guidelines?
- **Documentation**: Are changes documented?
- **Performance**: Any regressions?
- **Security**: Any vulnerabilities?

**Respond to feedback:**
- Address all comments
- Push additional commits (don't force-push during review)
- Re-request review when ready

### 8. Merging

Once approved:
- **Squash merge** for small changes (1-3 commits)
- **Rebase merge** for larger features (maintain history)
- **Delete branch** after merge

## Code Style Guidelines

### R Code Style

**Good:**
```r
#' Calculate team ratings based on game results
#'
#' @param game_df Data frame with game results
#' @param train_date Date for training cutoff
#' @return Data frame with team ratings
create_rating_df <- function(game_df, train_date) {
  game_df %>%
    filter(`Game Date` <= train_date) %>%
    group_by(Team) %>%
    summarise(
      Rating = mean(Score, na.rm = TRUE),
      Games = n()
    ) %>%
    arrange(desc(Rating))
}
```

**Bad:**
```r
# calc ratings
cr <- function(g, d) {
  x <- g %>% filter(`Game Date` <= d) %>% group_by(Team) %>% summarise(Rating = mean(Score, na.rm = TRUE), Games = n()) %>% arrange(desc(Rating))
  return(x)
}
```

### Comments

**Write comments for:**
- Complex algorithms (explain why, not what)
- Non-obvious optimizations
- Business logic decisions

**Don't write comments for:**
- Self-explanatory code
- Restating what code does

## Testing Guidelines

### What to Test

**Always test:**
- Public functions
- Edge cases
- Error handling
- Data transformations
- Critical business logic

**Don't need to test:**
- Simple getters/setters
- Trivial wrappers
- Private helper functions (test through public interface)

### Test Structure

```r
test_that("create_rating_df handles empty input", {
  # Arrange
  empty_df <- data.frame()

  # Act
  result <- create_rating_df(empty_df, Sys.Date())

  # Assert
  expect_equal(nrow(result), 0)
  expect_s3_class(result, "data.frame")
})

test_that("create_rating_df filters by train_date", {
  # Arrange
  game_df <- data.frame(
    Team = c("A", "A", "B"),
    Score = c(10, 20, 15),
    `Game Date` = as.Date(c("2024-01-01", "2024-01-15", "2024-01-10")),
    check.names = FALSE
  )
  train_date <- as.Date("2024-01-10")

  # Act
  result <- create_rating_df(game_df, train_date)

  # Assert
  # Should only include games on or before train_date
  expect_equal(nrow(result), 2)
})
```

## Documentation Guidelines

### When to Update Documentation

Update documentation when you:
- Add new features
- Change user-facing behavior
- Modify configuration options
- Change API contracts
- Fix bugs that affected documented behavior

### What to Document

**README.md:**
- Installation steps
- Usage examples
- Configuration options
- Common use cases

**CLAUDE.md:**
- Development setup
- Architecture overview
- Key commands
- Important patterns

**Code comments:**
- Complex algorithms
- Non-obvious decisions
- Workarounds for limitations

**CHANGELOG.md:**
- All user-facing changes
- Breaking changes
- Migration guides

## Getting Help

- **Questions**: Open a [discussion](https://github.com/cnoyes/ute-conference-rankings/discussions)
- **Bugs**: Open a [bug report](https://github.com/cnoyes/ute-conference-rankings/issues/new?template=bug_report.md)
- **Features**: Open a [feature request](https://github.com/cnoyes/ute-conference-rankings/issues/new?template=feature_request.md)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
