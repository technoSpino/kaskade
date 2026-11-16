# Contributing to German Declension Learning App

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

---

## Getting Started

### Prerequisites
- Git
- Web browser (Chrome, Firefox, Safari, or Edge)
- Code editor (VS Code, Sublime, etc.)
- Optional: Node.js for local server

### Setup
```bash
# Clone the repository
git clone https://github.com/technoSpino/kaskade.git
cd kaskade

# No build step needed - it's a static site!

# Start local server
cd app/
python -m http.server 8000
# Or: npx http-server -p 8000

# Visit http://localhost:8000
```

---

## Project Structure

```
kaskade/
├── README.md               Main documentation
├── PROJECT_PLAN.md         Execution timeline
├── agent-1-table/          Table module specs
├── agent-2-flashcard/      Flashcard module specs
├── agent-3-integration/    Integration specs
├── deployment/             Deployment configs
└── app/                    Source code (deploy this)
    ├── index.html
    ├── table.html
    ├── flashcards.html
    ├── styles.css
    └── app.js
```

---

## How to Contribute

### Reporting Bugs

1. **Search existing issues** first
2. **Create new issue** with:
   - Clear title
   - Steps to reproduce
   - Expected vs actual behavior
   - Browser/device info
   - Screenshots if relevant

Example:
```
Title: Flashcard modal doesn't close on ESC key in Safari

Steps:
1. Open flashcards.html in Safari
2. Click a card to open modal
3. Press ESC key

Expected: Modal closes
Actual: Modal stays open

Browser: Safari 17.0 on macOS
```

### Suggesting Features

1. **Check existing issues** for duplicates
2. **Create feature request** with:
   - Clear description
   - Use case (why it's needed)
   - Proposed solution (optional)
   - Mockups/examples (if relevant)

### Contributing Code

#### Small Changes (Typos, CSS tweaks)
1. Fork the repo
2. Create branch: `fix/typo-in-readme`
3. Make changes
4. Test locally
5. Submit pull request

#### Larger Changes (New features)
1. **Discuss first** - create an issue
2. Wait for approval/feedback
3. Fork and create feature branch
4. Implement changes
5. Write tests (if applicable)
6. Submit pull request

---

## Development Workflow

### Branch Naming
- `feature/add-pronunciation` - New features
- `fix/modal-close-bug` - Bug fixes
- `docs/update-readme` - Documentation
- `refactor/improve-css` - Code improvements

### Commit Messages
```bash
# Good
git commit -m "Fix: Modal ESC key handling in Safari"
git commit -m "Feature: Add dark mode toggle"
git commit -m "Docs: Update deployment instructions"

# Bad
git commit -m "fixed stuff"
git commit -m "updates"
```

Follow format: `Type: Description`
- **Feature**: New functionality
- **Fix**: Bug fix
- **Docs**: Documentation changes
- **Style**: Formatting, no logic change
- **Refactor**: Code restructuring
- **Test**: Adding tests

---

## Code Standards

### HTML
- Use semantic tags (`<section>`, `<nav>`, `<article>`)
- Proper heading hierarchy (h1 → h2 → h3)
- Add alt text to images
- Validate with W3C validator

### CSS
- Use CSS variables for colors
- Mobile-first approach
- BEM naming (optional): `.card__title--active`
- Avoid `!important`
- Comment complex selectors

Example:
```css
/* Good */
:root {
  --color-primary: #667eea;
  --spacing-md: 1rem;
}

.card {
  padding: var(--spacing-md);
  background: var(--color-primary);
}

/* Bad */
.card {
  padding: 16px !important;
  background: #667eea;
}
```

### JavaScript
- Use `const` and `let` (no `var`)
- Meaningful variable names
- Add comments for complex logic
- Handle errors gracefully
- Avoid global variables

Example:
```javascript
// Good
function scheduleNextReview(box) {
  const days = INTERVALS[box];
  const now = new Date();
  return now.getTime() + (days * 24 * 60 * 60 * 1000);
}

// Bad
function snr(b) {
  let d = i[b];
  let n = new Date();
  return n.getTime() + (d * 86400000);
}
```

---

## Testing

### Before Submitting PR

#### Functionality
- [ ] Feature works as intended
- [ ] No console errors
- [ ] LocalStorage persists correctly
- [ ] All existing features still work

#### Cross-Browser
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

#### Responsive
- [ ] Test at 320px (iPhone SE)
- [ ] Test at 768px (iPad)
- [ ] Test at 1920px (Desktop)

#### Accessibility
- [ ] Keyboard navigation works
- [ ] Focus indicators visible
- [ ] Color contrast sufficient (4.5:1)
- [ ] Screen reader friendly

#### Performance
- [ ] No significant slowdown
- [ ] Lighthouse score >90 maintained

---

## Pull Request Process

### 1. Before Creating PR
- Update from main: `git pull upstream main`
- Resolve conflicts
- Test thoroughly
- Update docs if needed

### 2. Create PR
**Good PR description:**
```markdown
## Description
Fixes modal close bug in Safari where ESC key doesn't work

## Changes
- Added ESC key event listener to modal component
- Tested on Safari 17.0
- Updated modal documentation

## Testing
- [x] Manual testing on Safari
- [x] Tested on Chrome (still works)
- [x] No console errors

## Screenshots
[Attach if relevant]

Closes #42
```

### 3. PR Checklist
- [ ] Code follows style guide
- [ ] Self-reviewed code
- [ ] Commented complex code
- [ ] Updated documentation
- [ ] No console warnings/errors
- [ ] Tested on multiple browsers
- [ ] Mobile responsive

### 4. Review Process
- Maintainers will review within 1-3 days
- Address feedback
- Request re-review when ready
- PR merged when approved

---

## Adding New Features

### Example: Adding a Dark Mode

1. **Create issue** first
   ```
   Title: Feature: Add dark mode toggle
   
   Description:
   Add a dark mode option to reduce eye strain.
   Should remember user preference in localStorage.
   
   Proposed UI:
   - Toggle in header (sun/moon icon)
   - Affects all pages
   - Smooth transition
   ```

2. **Wait for approval** from maintainers

3. **Implement**
   ```bash
   git checkout -b feature/add-dark-mode
   ```
   
   CSS:
   ```css
   [data-theme="dark"] {
     --bg-color: #1a1a1a;
     --text-color: #f0f0f0;
   }
   ```
   
   JavaScript:
   ```javascript
   function toggleDarkMode() {
     const current = document.body.dataset.theme;
     const next = current === 'dark' ? 'light' : 'dark';
     document.body.dataset.theme = next;
     localStorage.setItem('theme', next);
   }
   ```

4. **Test thoroughly**
5. **Create PR** with description, screenshots
6. **Address review feedback**

---

## Community Guidelines

### Be Respectful
- Assume good intentions
- Provide constructive feedback
- Welcome newcomers
- Celebrate contributions

### Be Patient
- Maintainers are volunteers
- Reviews take time
- Not all PRs will be merged

### Be Collaborative
- Discuss before big changes
- Accept feedback gracefully
- Help others learn

---

## Questions?

- **General questions**: Create a GitHub Discussion
- **Bug reports**: Create an Issue
- **Feature ideas**: Create an Issue with "feature request" label
- **Security issues**: Email maintainers directly (don't create public issue)

---

## Recognition

Contributors will be:
- Listed in README.md
- Thanked in release notes
- Part of the project's success!

---

Thank you for contributing! Every improvement, no matter how small, makes this project better for German learners worldwide. 🇩🇪
