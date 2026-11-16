# German A2 Grammar Learning Platform

A comprehensive, interactive web application for learning German grammar at the A2 level. Features multiple choice exercises, embedded flashcards, and structured lessons across 6 major grammar topics.

## 🎯 Features

### Grammar Topics Covered

1. **Declensions** - Articles and adjective endings with color-coded tables
2. **Modal Verbs** - können, müssen, wollen, möchten, dürfen, sollen
3. **Sentence Structure** - Hauptsatz and Nebensatz word order
4. **Verb Conjugation** - Regular, irregular, stem-changing, and separable verbs
5. **Past Tense (Perfekt)** - haben/sein + past participles
6. **Prepositions** - Akkusativ, Dativ, Two-Way, and Genitiv

### Learning Tools

- **📊 Interactive Tables** - Color-coded visual learning aids
- **✅ Multiple Choice Exercises** - 10+ exercises per topic with instant feedback
- **🎴 Embedded Flashcards** - Quick practice cards in each section
- **📚 Comprehensive Flashcard System** - Leitner spaced repetition with 55+ cards
- **📱 Mobile Responsive** - Works perfectly on all devices
- **💾 Progress Tracking** - LocalStorage-based progress persistence

## 🚀 Getting Started

### Prerequisites

- Node.js 18+ and npm

### Installation

```bash
# Clone the repository
git clone https://github.com/technoSpino/kaskade.git
cd kaskade/app

# Install dependencies
npm install

# Start development server
npm run dev
```

The app will be available at `http://localhost:5173`

### Building for Production

```bash
# Build the app
npm run build

# Preview the production build
npm run preview
```

## 🏗️ Architecture

### Technology Stack

- **Vue 3** - Progressive JavaScript framework
- **Vue Router** - Client-side routing
- **Tailwind CSS** - Utility-first CSS framework
- **Vite** - Next generation frontend tooling
- **Pinia** - State management

### Project Structure

```
app/
├── src/
│   ├── components/
│   │   ├── AppNav.vue                  # Navigation bar
│   │   ├── FlashcardCard.vue           # Flashcard component
│   │   ├── MultipleChoiceExercise.vue  # Reusable quiz component
│   │   └── EmbeddedFlashcards.vue      # Embedded flashcard component
│   ├── views/
│   │   ├── HomeView.vue                # Landing page
│   │   ├── TablesView.vue              # Declensions
│   │   ├── ModalVerbsView.vue          # Modal verbs
│   │   ├── SentenceStructureView.vue   # Sentence structure
│   │   ├── VerbConjugationView.vue     # Verb conjugation
│   │   ├── PastTenseView.vue           # Past tense
│   │   ├── PrepositionsView.vue        # Prepositions
│   │   └── FlashcardsView.vue          # Main flashcard system
│   ├── data/
│   │   ├── declensions.json            # Declension data
│   │   ├── modalVerbs.json             # Modal verb data
│   │   ├── sentenceStructure.json      # Sentence structure data
│   │   ├── verbConjugations.json       # Verb conjugation data
│   │   ├── pastTense.json              # Past tense data
│   │   ├── prepositions.json           # Preposition data
│   │   └── flashcards.json             # Flashcard data
│   ├── stores/
│   │   ├── flashcardStore.js           # Flashcard state management
│   │   └── progressStore.js            # Progress tracking
│   ├── router/
│   │   └── index.js                    # Route definitions
│   └── App.vue                         # Root component
├── index.html
└── package.json
```

## 📖 Usage

### For Learners

1. **Start with Tables** - Understand declension patterns with visual aids
2. **Practice Modal Verbs** - Learn conjugations and usage
3. **Master Sentence Structure** - Understand German word order
4. **Study Verb Conjugation** - Practice all verb types
5. **Learn Past Tense** - Master the Perfekt tense
6. **Review Prepositions** - Understand case requirements
7. **Use Flashcards** - Reinforce learning with spaced repetition

### Exercise System

Each topic includes:
- **Multiple choice quizzes** - Test your knowledge
- **Embedded flashcards** - Quick practice within each section
- **Immediate feedback** - Learn from mistakes instantly
- **Progress tracking** - See your improvement over time

## 🎨 Design Principles

- **Visual Learning** - Color-coded grammar concepts
- **Progressive Disclosure** - Information revealed as needed
- **Immediate Feedback** - Learn from mistakes right away
- **Spaced Repetition** - Scientifically-proven learning method
- **Mobile-First** - Optimized for learning on the go

## 🧪 Testing

```bash
# Run unit tests
npm run test

# Run end-to-end tests
npm run test:e2e
```

## 📝 Data Format

All grammar data is stored in JSON format for easy maintenance and extension:

```json
{
  "exercises": [
    {
      "id": 1,
      "question": "Complete: Ich _____ Deutsch sprechen. (can)",
      "options": ["kann", "kannst", "können", "könnt"],
      "correct": 0,
      "explanation": "First person singular (ich) of 'können' is 'kann'."
    }
  ],
  "flashcards": [
    {
      "id": 1,
      "front": "ich _____ (können)",
      "back": "ich kann",
      "explanation": "First person singular of 'können'"
    }
  ]
}
```

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Adding New Content

To add new grammar topics or exercises:

1. Create a new JSON file in `app/src/data/`
2. Create a corresponding view component in `app/src/views/`
3. Add the route to `app/src/router/index.js`
4. Update the navbar in `app/src/components/AppNav.vue`
5. Add a card to the home page in `app/src/views/HomeView.vue`

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Grammar content based on A2 level German standards
- Color scheme inspired by effective visual learning research
- Spaced repetition algorithm based on the Leitner system

## 📧 Contact

Project Link: [https://github.com/technoSpino/kaskade](https://github.com/technoSpino/kaskade)

---

**Happy Learning! Viel Erfolg! 🇩🇪**
