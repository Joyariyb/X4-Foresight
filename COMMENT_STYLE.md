# Comment Style Guide

## Philosophy

Comments should explain **WHY**, not **WHAT**. Code that reads well doesn't need comments explaining what it does.

- **Minimize**: Only comment when the WHY is non-obvious (hidden constraint, workaround, surprising behavior)
- **Never explain WHAT** — well-named code already does that
- **Explain WHY** — design decisions, constraints, subtle invariants, non-obvious behavior
- **No task references** — "for issue #123", "used by X", etc. belong in git history, not code

## Every Code File: Core Role Header

Every code file must have a **one-line core role statement** at the very top (after any shebang or module docstring).

**Purpose**: When code might belong in a different file, the core role makes scope boundaries crystal clear.

**Format**:
```
// Core role: [What this file owns and why it exists]
```

**Examples**:
- `ui/js/universe-map.js`: `// Core role: Renders the interactive galaxy map as a flat-top hex grid with zoom-driven visibility layers.`
- `gamefiles/generate_data.py`: `# Core role: Regenerates game-derived lookup tables by parsing X4's .cat/.dat archives.`
- `ui/css/base.css`: `/* Core role: Global CSS reset and theme variables (colors, fonts, spacing). */`
- `db/schema.sql`: `-- Core role: SQLite schema for scan history, trade ledger, and reference galaxy data.`

## By Language

### Python
```python
# Core role: [one-line purpose statement]

import sys
```

Single-line comments for brief explanation:
```python
# Explain hidden constraint or design decision here
variable = value
```

Multi-line for complex reasoning (rare, 1-3 sentences max):
```python
# Explain the subtle behavior or constraint that makes
# this approach necessary, not what the code does.
```

### JavaScript
```javascript
// Core role: [one-line purpose statement]

function myFunction() {
```

Single-line comments:
```javascript
// Explain why this approach is needed (constraint, workaround, etc.)
const value = compute();
```

Multi-line (wrapped at ~80 chars, 1-3 sentences max):
```javascript
// Explain why this is tricky. For example: QtWebEngine doesn't support X,
// so we use Y instead. OR: This modifies state in-place; callers expect that.
```

### CSS
```css
/* Core role: [one-line purpose statement] */

/* Use sparingly — only for non-obvious design choices */
.some-class {
```

### SQL
```sql
-- Core role: [one-line purpose statement]

-- Use single-line unless genuinely complex
CREATE TABLE ...
```

### HTML
```html
<!-- Core role: [one-line purpose statement] -->

<!-- Use rarely; only for structural clarity in complex layouts -->
```

## What to Delete

- **Restating names**: `// loop through items` above `for item in items:`
- **Explaining obvious operations**: `// add 1 to count`, `// set flag to true`
- **Historical notes**: `// before we had X`, `// used to do Y`
- **Task references**: `// for the UI fix`, `// handles case from PR #123`
- **Dated observations**: `// seems to work`, `// not sure why this is here`

## What to Keep

- **Workarounds**: `// QtWebEngine doesn't support X, so we use Y instead`
- **Non-obvious constraints**: `// Must be ASCII-only due to cp1252 console`
- **Subtle bugs**: `// This modifies state in-place; callers expect that`
- **Why unusual approach**: `// Intentionally not using X library because of Y limitation`
- **Key design decisions**: `// Kept separate to avoid conflating transport ship with far-end station`

## Example: Before and After

### Before (Over-commented)
```python
def calculate_budget(station):
    # Initialize total
    total = 0
    
    # Loop through each ware
    for ware in station.wares:
        # Check if ware is in supply config
        if ware.in_supply:
            # Get the storage amount
            storage = ware.storage
            # Calculate budget needed
            budget_needed = storage * ware.price
            # Add to total
            total += budget_needed
    
    return total
```

### After (Minimal, focused)
```python
def calculate_budget(station):
    # Budget is reverse-engineered, not stored in save — recompute from storage/trade config
    total = 0
    for ware in station.wares:
        if ware.in_supply:
            total += ware.storage * ware.price
    return total
```

---

**Last updated**: 2026-06-20  
**Applies to**: All tracked code files (Python, JavaScript, CSS, SQL, HTML)
