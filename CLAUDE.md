# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **German A2 Grammar Learning Platform** built with Vue 3, Vue Router, Tailwind CSS, and Vite. The application provides comprehensive interactive lessons, exercises, and flashcards for learning German grammar at the A2 level.

**Core Value Proposition:** Complete A2-level German grammar platform with color-coded visual learning, multiple choice exercises, embedded flashcards, and spaced repetition practice.

## Architecture

### Technology Stack

- **Vue 3** - Progressive JavaScript framework with Composition API
- **Vue Router** - Client-side routing for SPA navigation
- **Tailwind CSS** - Utility-first CSS framework
- **Vite** - Next generation frontend build tool
- **Pinia** - State management for flashcards and progress
- **JSON** - All grammar data stored in JSON files for easy maintenance

### Application Structure

The application consists of 7 main topic sections plus a comprehensive flashcard system:

1. **Declensions** (`/tables`) - Color-coded declension tables with adjective endings
2. **Modal Verbs** (`/modal-verbs`) - können, müssen, wollen, möchten, dürfen, sollen
3. **Sentence Structure** (`/sentence-structure`) - Hauptsatz and Nebensatz word order
4. **Verb Conjugation** (`/verb-conjugation`) - Regular, irregular, stem-changing, separable verbs
5. **Past Tense** (`/past-tense`) - Perfekt tense with haben/sein + past participles
6. **Prepositions** (`/prepositions`) - Akkusativ, Dativ, Two-Way, and Genitiv prepositions
7. **Flashcards** (`/flashcards`) - Leitner spaced repetition system with 55+ cards
8. **Home** (`/`) - Landing page with progress tracking and topic navigation

### Key Design Principles

- **JSON-based content:** All grammar data, exercises, and flashcards stored in JSON for maintainability
- **Reusable components:** MultipleChoiceExercise and EmbeddedFlashcards used across all topics
- **Embedded exercises:** Each topic includes both multiple choice quizzes and quick flashcards
- **LocalStorage persistence:** Progress tracking and flashcard state persisted client-side
- **Mobile-first responsive:** Optimized for all screen sizes (320px minimum)
- **Color-coded learning:** Consistent color scheme for cases (Nominativ=blue, Akkusativ=red, Dativ=green, Genitiv=orange)

## Development Commands

### Local Development

```bash
cd app

# Install dependencies
npm install

# Start development server
npm run dev
# Opens at http://localhost:5173

# Build for production
npm run build

# Preview production build
npm run preview
```

### Testing

```bash
# Run unit tests
npm run test

# Run end-to-end tests
npm run test:e2e

# Run tests in watch mode
npm run test:watch
```

## Code Structure

```
app/
├── src/
│   ├── components/
│   │   ├── AppNav.vue                  # Main navigation bar with all topics
│   │   ├── FlashcardCard.vue           # Individual flashcard display component
│   │   ├── MultipleChoiceExercise.vue  # Reusable quiz component
│   │   └── EmbeddedFlashcards.vue      # Embedded flashcard practice component
│   ├── views/
│   │   ├── HomeView.vue                # Landing page with topic cards
│   │   ├── TablesView.vue              # Declension tables view
│   │   ├── ModalVerbsView.vue          # Modal verbs lessons and exercises
│   │   ├── SentenceStructureView.vue   # Sentence structure lessons
│   │   ├── VerbConjugationView.vue     # Verb conjugation lessons
│   │   ├── PastTenseView.vue           # Past tense lessons
│   │   ├── PrepositionsView.vue        # Prepositions lessons
│   │   └── FlashcardsView.vue          # Main flashcard system
│   ├── data/                           # JSON data files
│   │   ├── declensions.json
│   │   ├── modalVerbs.json
│   │   ├── sentenceStructure.json
│   │   ├── verbConjugations.json
│   │   ├── pastTense.json
│   │   ├── prepositions.json
│   │   └── flashcards.json
│   ├── stores/
│   │   ├── flashcardStore.js           # Pinia store for flashcard state
│   │   └── progressStore.js            # Pinia store for progress tracking
│   ├── router/
│   │   └── index.js                    # Route definitions for all pages
│   ├── App.vue                         # Root component
│   └── main.js                         # Application entry point
├── index.html
├── package.json
├── tailwind.config.js
└── vite.config.js
```

## Working with Different Parts of the Application

### Adding a New Grammar Topic

1. **Create JSON data file** in `app/src/data/your-topic.json`:
```json
{
  "exercises": [
    {
      "id": 1,
      "question": "Your question here",
      "options": ["option1", "option2", "option3", "option4"],
      "correct": 0,
      "explanation": "Why this is correct"
    }
  ],
  "flashcards": [
    {
      "id": 1,
      "front": "Question",
      "back": "Answer",
      "explanation": "Additional context"
    }
  ]
}
```

2. **Create a View component** in `app/src/views/YourTopicView.vue`:
```vue
<script setup>
import { ref } from 'vue'
import MultipleChoiceExercise from '../components/MultipleChoiceExercise.vue'
import EmbeddedFlashcards from '../components/EmbeddedFlashcards.vue'
import topicData from '../data/your-topic.json'

const showExercises = ref(false)
const showFlashcards = ref(false)
</script>

<template>
  <!-- Your content here -->
  <EmbeddedFlashcards :flashcards="topicData.flashcards" title="Your Topic Practice" />
  <MultipleChoiceExercise :exercises="topicData.exercises" title="Your Topic Exercises" />
</template>
```

3. **Add route** to `app/src/router/index.js`:
```javascript
import YourTopicView from '../views/YourTopicView.vue'

const routes = [
  // ...existing routes
  {
    path: '/your-topic',
    name: 'YourTopic',
    component: YourTopicView,
    meta: { title: 'Your Topic' }
  }
]
```

4. **Update navbar** in `app/src/components/AppNav.vue` - Add links in both desktop and mobile menus

5. **Add to home page** in `app/src/views/HomeView.vue` - Add a topic card in the topics grid

### Working with Reusable Components

#### MultipleChoiceExercise Component

Props:
- `exercises` (Array, required) - Array of exercise objects
- `title` (String, default: 'Practice Exercises') - Section title

Features:
- Progress tracking with score display
- Immediate feedback on answers
- Explanations for each question
- Navigation between questions
- Final score summary

#### EmbeddedFlashcards Component

Props:
- `flashcards` (Array, required) - Array of flashcard objects
- `title` (String, default: 'Quick Practice') - Section title

Features:
- Flip animation
- Keyboard navigation (Space, Arrow keys)
- Progress counter
- Explanations on back of cards

## Color Scheme Reference

Cases use consistent color coding across all topics:

- **Nominativ:** Blue (#2196F3) - Background #E3F2FD
- **Akkusativ:** Red (#F44336) - Background #FFEBEE
- **Dativ:** Green (#4CAF50) - Background #E8F5E9
- **Genitiv:** Orange (#FF9800) - Background #FFF3E0

Additional colors:
- **Primary:** Violet (#7c3aed) - Used for buttons and highlights
- **Text:** Gray (#1f2937, #374151, #6b7280) - Various text levels

Ensure WCAG AA contrast ratios (4.5:1 minimum).

## LocalStorage Schema

```javascript
// Flashcard progress (Pinia store)
localStorage.setItem('flashcardProgress', JSON.stringify({
  cards: [{
    id: 1,
    box: 1,              // Leitner box 1-5
    nextReview: null,    // timestamp or null
    correctCount: 0,
    incorrectCount: 0,
    lastReviewed: null
  }],
  sessionStats: {
    cardsReviewed: 0,
    correctAnswers: 0,
    incorrectAnswers: 0
  }
}))

// Progress tracking (Pinia store)
localStorage.setItem('progress', JSON.stringify({
  cardsStudied: 10,
  cardsMastered: 5,
  tableInteractions: 20,
  currentStreak: 3,
  lastStudy: 1234567890
}))
```

## Testing Checklist

Before considering a feature complete:

- [ ] No JavaScript console errors
- [ ] Works on mobile (test at 320px width)
- [ ] LocalStorage persists correctly
- [ ] All interactive elements have hover/focus states
- [ ] Keyboard navigation works (Tab, Enter, Escape, Space, Arrows)
- [ ] Color contrast meets WCAG AA standards
- [ ] Loading states handle gracefully
- [ ] Error states are user-friendly
- [ ] Responsive across all breakpoints
- [ ] Works in Chrome, Firefox, Safari, Edge

## Common Pitfalls to Avoid

1. **JSON syntax errors** - Always validate JSON files before committing
2. **Missing router imports** - Import new view components in router/index.js
3. **Navbar path mismatches** - Ensure navbar links match router paths exactly
4. **Mobile responsiveness** - Test on small screens, use Tailwind responsive classes
5. **LocalStorage errors** - Handle private browsing mode gracefully
6. **Component prop types** - Ensure correct prop types are passed to components
7. **Hard-coded data** - Keep all content in JSON files, not in Vue components

## Git Workflow

When adding new features:

```bash
# Create feature branch
git checkout -b feature/new-grammar-topic

# Make changes and test
npm run dev
npm run test

# Commit changes
git add .
git commit -m "feat: Add new grammar topic with exercises"

# Push to remote
git push origin feature/new-grammar-topic

# Create pull request for review
```

## Code Style

Follow these conventions:

- **Vue:** Composition API with `<script setup>`
- **JavaScript:** Use `const` and `let` (never `var`)
- **Naming:** camelCase for variables, PascalCase for components
- **Comments:** Explain complex logic, not obvious code
- **Tailwind:** Use utility classes, avoid custom CSS when possible
- **JSON:** Consistent indentation, meaningful keys
- **File organization:** Group related code, use descriptive file names

## Success Criteria

The platform is successful when:

- ✅ All 6 grammar topics are complete with exercises and flashcards
- ✅ 10+ exercises per topic working correctly
- ✅ Multiple choice exercises provide immediate feedback
- ✅ Embedded flashcards work in each section
- ✅ Main flashcard system uses Leitner spaced repetition
- ✅ Progress tracking persists across sessions
- ✅ Mobile responsive on all devices (320px+)
- ✅ No console errors or warnings
- ✅ Fast loading (<2 seconds)
- ✅ Intuitive navigation and user experience

## Resources

- **Vue 3 docs:** https://vuejs.org/
- **Vue Router docs:** https://router.vuejs.org/
- **Tailwind CSS docs:** https://tailwindcss.com/
- **Pinia docs:** https://pinia.vuejs.org/
- **Vite docs:** https://vitejs.dev/

## Kaskade (branch `kaskade`, in progress)

This branch turns the app into **Kaskade**, a Refold-style A2/B1→B2 learning app with a FastAPI backend on the Hetzner box. The build brief, hard rules and milestones are in `docs/kaskade/TASK.md`; progress is tracked in `docs/kaskade/PROGRESS.md`; design mockups are in `design/kaskade-mockups/`. The repo is public — never commit book content, exam material, third-party media, user data or secrets.
