#!/usr/bin/env python3
"""Rule-based customer support chatbot.

Loads greetings and FAQs from a JSON file, matches user input with
regular expressions and keyword scoring, keeps simple conversation state
(greeting -> listening -> resolved -> exit) and falls back gracefully when
it is not confident about an answer.

Usage:
    python chatbot.py                 # uses sample_faq.json next to this script
    python chatbot.py my_faq.json     # use a different FAQ file
"""

import json
import os
import re
import sys

DEFAULT_FAQ_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_faq.json")

# Used only if the JSON file is missing or broken.
FALLBACK_DATA = {
    "greetings": ["hello", "hi", "hey", "good morning", "good afternoon"],
    "faqs": [
        {
            "question": "What are your hours of operation?",
            "answer": "We operate Monday through Friday from 9:00 AM to 6:00 PM IST.",
        },
    ],
}

DEFAULT_HOURS = "We operate Monday through Friday from 9:00 AM to 6:00 PM IST."

# Confidence thresholds for FAQ matching (see Chatbot.best_match)
MATCH_SCORE = 0.40      # answer straight away at or above this
CONFIRM_SCORE = 0.25    # between CONFIRM_SCORE and MATCH_SCORE: ask "did you mean ...?"

# ----------------------------------------------------------------------------
# Text normalisation
# ----------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "do", "does", "did",
    "i", "me", "my", "you", "your", "we", "our", "it", "its", "to", "of", "for",
    "in", "on", "at", "and", "or", "can", "could", "would", "will", "shall",
    "should", "how", "what", "whats", "when", "where", "which", "who", "why",
    "please", "tell", "about", "with", "this", "that", "there", "any", "some",
    "if", "so", "much", "many", "want", "need", "know", "im", "ive", "u", "ur",
}

# Different ways of saying the same thing map to one canonical word.
SYNONYMS = {
    "hours": "hour", "timing": "hour", "timings": "hour", "open": "hour",
    "opening": "hour", "closing": "hour", "close": "hour", "operation": "hour",
    "operate": "hour", "operating": "hour", "schedule": "hour",
    "get": "receive", "got": "receive", "getting": "receive", "obtain": "receive",
    "issued": "receive", "issue": "receive", "issuing": "receive",
    "received": "receive", "receiving": "receive",
    "submitted": "submit", "submission": "submit", "submissions": "submit",
    "upload": "submit", "uploading": "submit", "send": "submit",
    "repo": "repository", "repos": "repository", "repositories": "repository",
    "url": "link", "links": "link",
}

EXIT_RE = re.compile(r"\b(bye|goodbye|exit|quit)\b")
YES_RE = re.compile(r"^(yes|yeah|yep|yup|sure|ok|okay|please|y)$")
NO_RE = re.compile(
    r"^(no|nope|nah|n|nothing|no thanks|no thank you|that'?s all|thats all|"
    r"that is all|i'?m good|im good|all good|i am good)$"
)
THANKS_RE = re.compile(r"\b(thanks|thank you|thx|thankyou)\b")
NAME_RE = re.compile(r"\b(?:my name is|call me)\s+([a-z]+)")
HELP_RE = re.compile(r"\b(help|menu|options|topics|what can you do)\b")
REPEAT_RE = re.compile(r"^(repeat|again|say that again|repeat that|tell me more|what was that)\b|\brepeat that\b")
HOURS_RE = re.compile(
    r"\b(hours?|timings?|opening|closing|operation|operate|operating)\b"
    r"|\bwhat time\b"
    r"|\b(?:are|is)\s+(?:you|we|the \w+)\s+(?:open|closed|available)\b"
    r"|\bwhen\b.*\b(?:open|close)\b"
)
WEEKEND_RE = re.compile(r"\b(saturday|sunday|weekend|weekends)\b")


def normalize(text):
    """Lowercase, strip punctuation (keep apostrophes) and collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stem(word):
    """Very small suffix stripper so 'projects' matches 'project'."""
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def canon(word):
    """Map a raw word to its canonical form (synonym or stem)."""
    if word in SYNONYMS:
        return SYNONYMS[word]
    s = stem(word)
    return SYNONYMS.get(s, s)


def keywords(text):
    """Set of canonical, non-stopword tokens in a piece of text."""
    tokens = re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))
    return {canon(t) for t in tokens if t not in STOPWORDS}


# ----------------------------------------------------------------------------
# Chatbot
# ----------------------------------------------------------------------------

class Chatbot:
    """Conversation states: listening -> (confirming) -> resolved -> exit."""

    def __init__(self, data):
        self.entries = []
        for item in data.get("faqs", []):
            if "question" in item and "answer" in item:
                q = keywords(item["question"])
                a = keywords(item["answer"]) - q
                self.entries.append(
                    {"question": item["question"], "answer": item["answer"], "q": q, "a": a}
                )

        greetings = sorted(data.get("greetings", []), key=len, reverse=True)
        self.greeting_re = (
            re.compile(r"^(" + "|".join(re.escape(g.lower()) for g in greetings) + r")\b\s*")
            if greetings else None
        )

        self.state = "listening"
        self.name = None
        self.last_answer = None
        self.pending = None   # FAQ entry waiting for a yes/no confirmation
        self.misses = 0       # consecutive unrecognised messages

    # -- helpers -------------------------------------------------------------

    def opening(self):
        return "Hello! I'm the support assistant. Ask me a question, or type 'help' to see topics. Type 'bye' to exit."

    def goodbye(self):
        who = f", {self.name}" if self.name else ""
        return f"Thanks for chatting{who}. Goodbye!"

    def topics(self):
        lines = "\n".join(f"  - {e['question']}" for e in self.entries)
        return f"Here's what I can help with:\n{lines}"

    def answer(self, text):
        self.last_answer = text
        self.state = "resolved"
        self.misses = 0
        return f"{text}\nIs there anything else I can help with?"

    def best_match(self, text):
        """Return (entry, matched_weight, score) for the best FAQ, or (None, 0, 0).

        Each user keyword counts 1.0 if it appears in an FAQ question and 0.5 if it
        only appears in the FAQ answer. score = matched weight / number of user keywords,
        i.e. how much of what the user said is explained by that FAQ.
        """
        user = keywords(text)
        best, best_weight, best_score = None, 0.0, 0.0
        if not user:
            return best, best_weight, best_score
        for entry in self.entries:
            weight = sum(1.0 if t in entry["q"] else 0.5 if t in entry["a"] else 0.0 for t in user)
            score = weight / len(user)
            if (weight, score) > (best_weight, best_score):
                best, best_weight, best_score = entry, weight, score
        return best, best_weight, best_score

    def fallback(self):
        self.misses += 1
        self.state = "listening"
        if self.misses == 1:
            return "Sorry, I'm not sure I understand. Could you rephrase that? Type 'help' to see what I can answer."
        return f"I still couldn't match that. {self.topics()}\nOr type 'bye' to exit."

    # -- main entry point ----------------------------------------------------

    def respond(self, raw):
        """Return (reply, finished)."""
        text = normalize(raw)
        if not text:
            return "I didn't catch that. Could you type your question?", False

        if EXIT_RE.search(text):
            return self.goodbye(), True

        # Waiting for yes/no on a low-confidence suggestion
        if self.state == "confirming" and self.pending:
            entry, self.pending = self.pending, None
            self.state = "listening"
            if YES_RE.match(text):
                return self.answer(entry["answer"]), False
            if NO_RE.match(text):
                return "No problem. Could you rephrase your question, or type 'help' to see topics?", False
            # anything else is treated as a brand-new question

        # Waiting to hear whether the user needs anything else
        if self.state == "resolved":
            if NO_RE.match(text):
                return self.goodbye(), True
            if YES_RE.match(text):
                self.state = "listening"
                return "Sure, what would you like to know?", False

        # Greeting (possibly followed by a real question: "hi, what are your hours?")
        prefix = ""
        match = self.greeting_re.match(text) if self.greeting_re else None
        if match:
            greeting = match.group(1).capitalize()
            rest = text[match.end():].strip()
            if not rest:
                self.state = "listening"
                who = f", {self.name}" if self.name else ""
                return f"{greeting}{who}! How can I help you today? Type 'help' to see topics.", False
            prefix, text = f"{greeting}! ", rest

        return prefix + self.route(text), False

    def route(self, text):
        if THANKS_RE.search(text):
            self.state = "resolved"
            return "You're welcome! Is there anything else I can help with?"

        name = NAME_RE.search(text)
        if name:
            self.name = name.group(1).title()
            self.state = "listening"
            return f"Nice to meet you, {self.name}! What can I help you with?"

        if HELP_RE.search(text):
            self.state = "listening"
            return self.topics()

        if REPEAT_RE.search(text):
            if self.last_answer:
                return self.answer(self.last_answer)
            return "I haven't answered anything yet. Go ahead and ask me a question!"

        if HOURS_RE.search(text):
            entry = next((e for e in self.entries if "hour" in e["q"]), None)
            reply = entry["answer"] if entry else DEFAULT_HOURS
            if WEEKEND_RE.search(text):
                reply = "Weekends aren't part of our listed hours. " + reply
            return self.answer(reply)

        entry, weight, score = self.best_match(text)
        if entry and weight >= 1.0 and score >= MATCH_SCORE:
            return self.answer(entry["answer"])
        if entry and weight >= 0.5 and score >= CONFIRM_SCORE:
            self.pending = entry
            self.state = "confirming"
            return f'I\'m not completely sure. Did you mean: "{entry["question"]}" (yes/no)'

        return self.fallback()


# ----------------------------------------------------------------------------
# Command-line interface
# ----------------------------------------------------------------------------

def load_faq(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[note] Could not load '{path}' ({type(exc).__name__}). Using built-in FAQ data.")
        return FALLBACK_DATA


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FAQ_PATH
    bot = Chatbot(load_faq(path))

    print("=" * 52)
    print(" Support Chatbot")
    print("=" * 52)
    print("Bot:", bot.opening())

    try:
        while True:
            reply, finished = bot.respond(input("You: "))
            print("Bot:", reply)
            if finished:
                break
    except (KeyboardInterrupt, EOFError):
        print("\nBot:", bot.goodbye())


if __name__ == "__main__":
    main()