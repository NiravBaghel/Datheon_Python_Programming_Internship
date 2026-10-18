#!/usr/bin/env python3
"""Terminal Hangman: guess the hidden word letter by letter within 6 mistakes."""

import os
import random

MAX_MISTAKES = 6

# Fallback word list, used when no words.txt file sits next to this script.
DEFAULT_WORDS = [
    "python", "variable", "function", "algorithm", "database", "keyboard",
    "network", "compiler", "software", "hardware", "internet", "browser",
    "developer", "terminal", "library", "module", "program", "debugging",
    "database", "encryption", "framework", "interface", "iteration",
    "recursion", "boolean", "integer", "string", "dictionary", "analysis",
    "machine", "learning", "dataset", "pandas", "matplotlib", "scraping",
]

# One ASCII picture per mistake count (index 0 = no mistakes, 6 = hanged).
STAGES = [
    """
      +---+
      |   |
          |
          |
          |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
          |
          |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
      |   |
          |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
     /|   |
          |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
     /|\\  |
          |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
     /|\\  |
     /    |
          |
    =========
    """,
    """
      +---+
      |   |
      O   |
     /|\\  |
     / \\  |
          |
    =========
    """,
]


def load_words():
    """Load words from words.txt (one per line) if present, else use the built-in list."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "words.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            words = [w.strip().lower() for w in f if w.strip().isalpha() and len(w.strip()) >= 4]
        if words:
            return words
    return DEFAULT_WORDS


def masked(word, correct):
    """Return the word with unguessed letters hidden, e.g. '_ A _ H E O N'."""
    return " ".join(ch.upper() if ch in correct else "_" for ch in word)


def read_guess(correct, wrong):
    """Prompt until the player enters a valid, not-yet-guessed single letter."""
    while True:
        raw = input("Guess a letter: ").strip().lower()
        if len(raw) != 1 or not raw.isalpha():
            print("  Please enter a single letter (A-Z).")
        elif raw in correct or raw in wrong:
            print(f"  You already guessed '{raw.upper()}'. No penalty, try another.")
        else:
            return raw


def play_round(word):
    correct = set()   # right letters
    wrong = set()     # wrong letters (len(wrong) == number of mistakes)
    letters_needed = set(word)

    print("\n=== HANGMAN ===")
    print(f"The word has {len(word)} letters. You may make {MAX_MISTAKES} mistakes.")

    while len(wrong) < MAX_MISTAKES and not letters_needed <= correct:
        print(STAGES[len(wrong)])
        print("Word:   ", masked(word, correct))
        print("Wrong:  ", " ".join(sorted(c.upper() for c in wrong)) or "-")
        print(f"Lives:   {MAX_MISTAKES - len(wrong)}\n")

        guess = read_guess(correct, wrong)
        if guess in word:
            correct.add(guess)
            print(f"  Good guess! '{guess.upper()}' is in the word.")
        else:
            wrong.add(guess)
            print(f"  Sorry, '{guess.upper()}' is not in the word.")

    print(STAGES[len(wrong)])
    print("Word:   ", masked(word, correct | set(word)) if len(wrong) == MAX_MISTAKES
          else masked(word, correct))
    if letters_needed <= correct:
        print(f"\nYou won with {MAX_MISTAKES - len(wrong)} lives left!")
    else:
        print(f"\nYou lost. The word was '{word.upper()}'.")


def main():
    words = load_words()
    try:
        while True:
            play_round(random.choice(words))
            again = input("\nPlay again? (y/n): ").strip().lower()
            if again not in ("y", "yes"):
                break
    except (KeyboardInterrupt, EOFError):
        pass
    print("\nThanks for playing!")


if __name__ == "__main__":
    main()