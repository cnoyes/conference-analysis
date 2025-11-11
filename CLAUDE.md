# CLAUDE.md Template

Copy this template to new repositories and customize the Project Overview section.

---

# CLAUDE.md

This file provides **mandatory instructions** to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ MANDATORY PRACTICES

**READ FIRST**: Before starting any work, read `.claude/BEST_PRACTICES.md` for comprehensive development guidelines.

**You MUST:**
1. ✅ Create feature branches for all non-trivial work (NEVER commit directly to main)
2. ✅ Create GitHub issues before starting features
3. ✅ Use plan mode for features requiring 3+ file changes
4. ✅ Invoke code-reviewer agent before creating PRs
5. ✅ Follow conventional commit format
6. ✅ Write tests for new features
7. ✅ Update documentation for user-facing changes

**Branch naming**: `<type>/<issue-number>-<brief-description>`
**Commit format**: `<type>(<scope>): <subject>` (see BEST_PRACTICES.md)

---

## Project Overview

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

[Brief description of what this project does]

## Key Commands

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

### Running the Application
```bash
# Example commands
npm start
python main.py
Rscript run.R
```

### Testing
```bash
# Example test commands
npm test
pytest
R CMD check
```

### Development Setup
```bash
# Example setup commands
npm install
pip install -r requirements.txt
R -e "renv::restore()"
```

## Development Workflow

For this project, always:
- Create feature branches from main
- Write tests before implementation (TDD)
- Run full test suite before creating PRs
- Reference issue numbers in commits and PRs

### Branch Naming
Use descriptive branch names with prefixes:
- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `refactor/` - Code improvements without behavior changes
- `docs/` - Documentation updates

### Commit Messages
Follow conventional commit format:
```
type(scope): brief description

- Reference issue numbers with #123
- Explain what changed and why
- Keep first line under 72 characters
```

## Architecture

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

### Key Components
1. **Component A**: Description
2. **Component B**: Description
3. **Component C**: Description

### Data Flow
```
Input → Process → Output
```

### Important Files
- `path/to/important/file.ext`: Description
- `path/to/config.ext`: Configuration

## Important Configuration

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

### Environment Variables
```bash
VAR_NAME=value  # Description
```

### Configuration Files
- `.config/file.yml`: Description of what this configures

## Common Patterns

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

### Pattern 1: [Name]
Description and example

### Pattern 2: [Name]
Description and example

## Troubleshooting

<!-- CUSTOMIZE THIS SECTION FOR YOUR PROJECT -->

### Common Issues
1. **Issue**: Description
   **Solution**: How to fix

2. **Issue**: Description
   **Solution**: How to fix
