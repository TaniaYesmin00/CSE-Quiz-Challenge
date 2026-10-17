<p align="center">
  <img src="assets/banner.png" alt="CSE Quiz Challenge banner" width="100%">
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Pygame" src="https://img.shields.io/badge/built%20with-pygame-5BBA47">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Tests" src="https://github.com/YOUR-USERNAME/CSE-Quiz-Challenge/actions/workflows/tests.yml/badge.svg">
</p>

# CSE Quiz Challenge

A polished desktop quiz game for Computer Science and Engineering students, built with **Python** and **Pygame**. Answer CSE questions against the clock, build streaks, protect your three lives, and chase a new personal best.


## Features

- **67 questions** across 8 CSE topics: Programming, Data Structures, Algorithms, Database, OOP, Operating Systems, Computer Networks and Digital Logic
- Pick a **difficulty** (Easy / Medium / Hard / All) and a **category**
- 10-question rounds, **20-second timer**, **3 lives**
- **50:50 lifeline**, once per round
- Score = base points + **streak bonus** + **speed bonus**
- Answer options are shuffled every round, so you cannot memorise positions
- **Review your mistakes** at the end of a round, then play again
- Letter grades (S / A / B / C), confetti for a new personal best
- Smooth animations, synthesised sound effects (no audio files), fullscreen with `F11`
- **Player accounts**: register with a username and password, then log in next time
- **Personal dashboard**: best score, games played, best streak, accuracy, your last 5 games and a top-5 leaderboard
- **SQLite database** (`data/quiz.db`) stores accounts and every game you finish; passwords are salted and hashed, never saved in plain text
- Prefer not to sign up? **Play as guest** (scores are not saved)
- Questions live in a JSON file, so you can add your own without touching the code

## Quick start

You need **Python 3.10+** and a desktop display (Windows, macOS or Linux).

```bash
git clone https://github.com/YOUR-USERNAME/CSE-Quiz-Challenge.git
cd CSE-Quiz-Challenge

python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate

python -m pip install -r requirements.txt
python main.py
```

On Windows, if `python` is not recognised, use `py` instead (`py -m venv .venv`, `py main.py`).

## Controls

| Action | Keys / mouse |
| --- | --- |
| Choose an answer | Click, or `A` `B` `C` `D` / `1` `2` `3` `4` |
| 50:50 lifeline | `F` or the 50:50 button |
| Skip the feedback delay | `Enter` / `Space` |
| Pause / resume | `P` or `Esc` |
| Mute / unmute | `M` |
| Fullscreen | `F11` |
| Browse mistakes | `Left` / `Right` arrow |
| Back / quit | `Esc` (quits from the login screen and dashboard) |
| Login form | `Tab` next field, `Enter` submit |

## Scoring

| Part | Points |
| --- | --- |
| Correct answer | 100 |
| Streak bonus | +20 for each answer in a row (up to +100) |
| Speed bonus | up to +50, the faster you answer |

A wrong answer or a timeout costs one life and resets your streak. The round ends when you run out of lives or finish all questions.

## Accounts and database

- On the first screen choose **Register**, type a username (3-16 letters, numbers or `_`) and a password (4 or more characters), then press `Enter`.
- After logging in you land on your **dashboard**. Press **PLAY NOW**, pick a difficulty and category, and start.
- Every finished round is saved to your profile, and the dashboard updates straight away.
- Everything is stored locally in `data/quiz.db` (SQLite, created automatically). The file is ignored by Git, so no one's accounts or scores get uploaded. Delete the file to reset all accounts.

Tables: `users` (username, salted password hash, created / last login) and `games` (score, correct answers, streak, grade, difficulty, category, time).

> This is a local single-computer game, so accounts exist to keep separate player profiles, not for online security.

## Add your own questions

Open `data/questions.json` and add an object like this:

```json
{
  "category": "Programming",
  "difficulty": "Easy",
  "question": "What does CPU stand for?",
  "options": ["Central Processing Unit", "Computer Personal Unit", "Control Program Utility", "Core Processing User"],
  "answer": 0
}
```

- `answer` is the zero-based index of the correct option (`0` is the first one).
- `difficulty` must be `Easy`, `Medium` or `Hard`.
- Use 2 to 4 options, with no duplicates.
- New categories appear in the menu automatically.

The game checks the file when it starts and tells you which question is wrong if something is invalid.

## Run the tests

The game rules are separated from the drawing code (`quiz_logic.py`), so they can be tested without a window:

```bash
python -m unittest discover -s tests -v
```

The tests cover scoring, lives, streaks, the 50:50 lifeline, registration, login, password hashing, game history and the leaderboard, and they validate every question in the bundled question bank.

## Project structure

```text
CSE-Quiz-Challenge/
├── main.py              # Pygame window, drawing, input, sound
├── quiz_logic.py        # Game rules, scoring, question loading (no pygame)
├── database.py          # SQLite: accounts, game history, leaderboard (no pygame)
├── data/
│   └── questions.json   # Editable question bank (quiz.db is created here on first run)
├── tests/               # Unit tests for the logic and the database
├── assets/banner.png    # README banner
├── .github/workflows/   # CI: runs the tests on every push
├── requirements.txt
├── LICENSE              # MIT
└── README.md
```


## Troubleshooting

- **`ModuleNotFoundError: No module named 'pygame'`**: run `python -m pip install -r requirements.txt` with the same Python you use to start the game.
- **No window in an online notebook or Codespace**: Pygame needs a desktop display. Run the game locally.
- **No sound**: the game continues silently if no audio device is found. Press `M` to toggle sound.
- **Database error on start**: make sure the project folder is writable. The game still works in guest mode without a database.
- **Forgot your password**: there is no reset yet. Register a new username, or delete `data/quiz.db` to start fresh.
- **Question file error**: the message names the question that is wrong. Check `data/questions.json` for valid JSON.

## Ideas for the future

- Timed "survival" and "speed" modes
- Question packs for more topics (Computer Architecture, Software Engineering, AI)
- Bengali / English language toggle
- Online leaderboard
- Password reset and profile pictures

## Author

**Tania Yesmin** - B.Sc. student in Computer Science and Engineering.

## License

Released under the [MIT License](LICENSE).
