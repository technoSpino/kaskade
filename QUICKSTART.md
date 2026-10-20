# Quick Start Guide

Get the German Declension Learning App running in minutes!

---

## For Developers (Using Claude Code)

### Option 1: Sequential Execution (Recommended for Solo)

```bash
# 1. Extract the zip
unzip kaskade.zip
cd kaskade

# 2. Week 1: Build Table Module
cd agent-1-table
cat SPEC.md
# Use Claude Code to build table module

# 3. Week 2: Build Flashcard Module
cd ../agent-2-flashcard
cat SPEC.md
# Use Claude Code to build flashcard module

# 4. Week 3: Integration & Deploy
cd ../agent-3-integration
cat SPEC.md
# Use Claude Code to integrate and deploy
```

### Option 2: Parallel Execution (Team)

```bash
# Developer 1
cd agent-1-table
# Follow SPEC.md

# Developer 2 (simultaneously)
cd agent-2-flashcard
# Follow SPEC.md

# Developer 3 (after 1 & 2 complete)
cd agent-3-integration
# Follow SPEC.md
```

---

## For End Users (Testing the App)

### Local Testing

```bash
# Extract zip
unzip kaskade.zip
cd kaskade/app

# Start local server (choose one):
python -m http.server 8000
# or
npx http-server -p 8000

# Visit http://localhost:8000
```

### Production Site

Once deployed, visit: `https://your-site.netlify.app`

---

## Project Structure at a Glance

```
kaskade/
├── README.md              ← Start here!
├── PROJECT_PLAN.md        ← 3-week timeline
│
├── agent-1-table/         ← Week 1
│   ├── SPEC.md           ← Full requirements
│   └── README.md         ← Quick reference
│
├── agent-2-flashcard/     ← Week 2
│   ├── SPEC.md
│   └── README.md
│
├── agent-3-integration/   ← Week 3
│   ├── SPEC.md
│   └── README.md
│
├── deployment/            ← Deploy configs
│   ├── DEPLOY.md         ← Deployment guide
│   ├── netlify.toml
│   └── _redirects
│
└── app/                   ← Final product goes here
    └── (created during development)
```

---

## First Time Setup

### 1. Read the Overview
```bash
cat README.md
```

### 2. Understand the Plan
```bash
cat PROJECT_PLAN.md
```

### 3. Start with Agent 1
```bash
cd agent-1-table
cat SPEC.md
```

### 4. Use Claude Code
```bash
# In agent-1-table directory
claude-code "Build the table module according to SPEC.md"
```

---

## Common Commands

### Development
```bash
# Start local server
python -m http.server 8000
# or
npx http-server app -p 8000

# Open in browser
open http://localhost:8000
```

### Git Setup
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/repo.git
git push -u origin main
```

### Deploy to Netlify (Easiest)
```bash
# Option 1: Drag & drop
# Visit https://app.netlify.com/drop
# Drag the app/ folder

# Option 2: CLI
netlify deploy --prod --dir=app
```

---

## Testing Checklist

Before considering an agent complete:

### Agent 1: Table Module
- [ ] All 5 tables display
- [ ] Colors work correctly
- [ ] Click cells → show examples
- [ ] Mobile responsive
- [ ] No console errors

### Agent 2: Flashcard Module
- [ ] 50 cards generated
- [ ] Study mode works
- [ ] Leitner scheduling correct
- [ ] LocalStorage persists
- [ ] Stats accurate

### Agent 3: Integration
- [ ] All pages linked
- [ ] Navigation works
- [ ] Progress syncs
- [ ] Deployed successfully
- [ ] Mobile tested

---

## Troubleshooting

### Can't start local server?
```bash
# Try alternative:
npx http-server app -p 8000
```

### Changes not showing?
- Hard refresh: Ctrl+Shift+R (Win) or Cmd+Shift+R (Mac)
- Clear browser cache
- Check console for errors

### LocalStorage not working?
- Check if using HTTPS (required for some browsers)
- Not in incognito/private mode
- Check browser storage settings

---

## Getting Help

- **Read the specs**: Each agent has detailed SPEC.md
- **Check examples**: Specs include code examples
- **Deployment guide**: See `deployment/DEPLOY.md`
- **Create issue**: If stuck, create GitHub issue

---

## Success Metrics

### Week 1
✅ Table module complete and tested

### Week 2
✅ Flashcard module complete and tested

### Week 3
✅ Integrated app deployed to production

### Week 4
✅ 5 users tested, feedback collected

---

## Next Steps

1. ✅ Read main README.md
2. ✅ Review PROJECT_PLAN.md
3. ✅ Start with agent-1-table/SPEC.md
4. ✅ Build with Claude Code
5. ✅ Test thoroughly
6. ✅ Move to next agent
7. ✅ Deploy and celebrate! 🎉

---

**Ready? Let's build!** 🚀

Start with: `cd agent-1-table && cat SPEC.md`
