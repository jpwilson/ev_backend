export type Subject = {
  id: string;
  name: string;
  emoji: string;
  blurb: string;
};

export const SUBJECTS: Subject[] = [
  { id: "algebra", name: "Algebra", emoji: "➗", blurb: "equations, functions, polynomials" },
  { id: "calculus", name: "Calculus", emoji: "∫", blurb: "limits, derivatives, integrals" },
  { id: "statistics", name: "Statistics", emoji: "📊", blurb: "probability, inference, distributions" },
  { id: "physics", name: "Physics", emoji: "🪐", blurb: "mechanics, E&M, modern physics" },
  { id: "chemistry", name: "Chemistry", emoji: "⚗️", blurb: "atoms, reactions, equilibria" },
  { id: "biology", name: "Biology", emoji: "🧬", blurb: "cells, genetics, evolution" },
  { id: "cs", name: "Computer Science", emoji: "💻", blurb: "algorithms, data structures, systems" },
  { id: "ml", name: "Machine Learning", emoji: "🤖", blurb: "models, training, evaluation" },
  { id: "econ", name: "Economics", emoji: "💹", blurb: "micro, macro, game theory" },
  { id: "finance", name: "Finance", emoji: "💰", blurb: "valuation, markets, accounting" },
  { id: "history", name: "World History", emoji: "🏛️", blurb: "civilizations, eras, causes" },
  { id: "geography", name: "Geography", emoji: "🌍", blurb: "physical and human geography" },
  { id: "english", name: "English & Writing", emoji: "✍️", blurb: "grammar, composition, rhetoric" },
  { id: "literature", name: "Literature", emoji: "📚", blurb: "analysis, themes, criticism" },
  { id: "spanish", name: "Spanish", emoji: "🇪🇸", blurb: "vocabulary, grammar, conversation" },
  { id: "french", name: "French", emoji: "🇫🇷", blurb: "vocabulary, grammar, conversation" },
  { id: "music", name: "Music Theory", emoji: "🎼", blurb: "scales, harmony, ear training" },
  { id: "art", name: "Art History", emoji: "🎨", blurb: "movements, artists, technique" },
  { id: "philosophy", name: "Philosophy", emoji: "🧠", blurb: "logic, ethics, metaphysics" },
  { id: "sat", name: "SAT Prep", emoji: "🎯", blurb: "math, reading, writing strategies" },
];

export function getSubject(id: string | null | undefined): Subject | null {
  if (!id) return null;
  return SUBJECTS.find((s) => s.id === id) ?? null;
}
