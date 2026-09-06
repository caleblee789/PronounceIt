# ChatGPT Pro Voice Pilot

This pilot compares ChatGPT Pro Voice with PronounceIt's current Azure audio for
60 representative medical terms. It is evaluation evidence only. ChatGPT Voice
audio must not be recorded, extracted, bundled, or treated as a distributable
audio asset.

Official OpenAI documentation describes Voice as a live conversation in which
typed input can receive a spoken response. It does not document a bulk audio-file
export workflow:

- https://help.openai.com/en/articles/20001274
- https://help.openai.com/en/articles/9793128-chatgpt-pro

## 1. Prepare the review kit

From the repository root, run:

```bash
python3 scripts/audio/pro_voice_pilot.py prepare
```

This creates `build/pro_voice_pilot/` containing:

- one CSV scoring sheet;
- six ready-to-paste Voice prompts;
- a manifest binding the pilot to the current dictionary and Azure references.

The command refuses to overwrite an existing review directory. Use a different
`--output-dir` to start another run.

## 2. Configure ChatGPT Voice

Use a personal ChatGPT Pro workspace and select:

- Voice: **Cove**
- Language: **English (United States)**
- Intelligence: **High**
- Speaking speed: normal/default

Start a new Voice chat for each session. While Voice is active, paste that
session's prompt as text. Do not add pronunciation hints or the existing
PronounceIt respelling.

## 3. Compare each term

Listen to the ChatGPT Voice pronunciation, then play the current PronounceIt
audio listed in the CSV:

- `audio/...mp3` references are bundled files in this checkout.
- `offline-pack:<asset>.mp3` references are available through PronounceIt after
  the complete offline pack is installed.

Enter integer scores from 1 to 5 for both systems:

- **Accuracy:** conformity with common U.S. medical pronunciation.
- **Naturalness:** fluent, intelligible, and easy for a student to imitate.
- **Pro serious error:** `yes` only for a materially wrong medical
  pronunciation; otherwise `no`.
- **Notes:** optional concise explanation.

Do not edit the identifying columns. Review every row.

## 4. Produce the decision report

```bash
python3 scripts/audio/pro_voice_pilot.py summarize
```

ChatGPT Pro wins an item only when its accuracy is at least 4 and its combined
accuracy/naturalness score is higher than Azure's. The pilot passes only when:

- all 60 terms are reviewed;
- Pro wins at least 48 terms (80%); and
- Pro has zero serious medical-pronunciation errors.

A pass makes OpenAI eligible for a separately controlled Speech API pilot. It
does not approve an API model, voice, or full-corpus migration because ChatGPT
Voice and the Speech API are different production interfaces.

No source, package, dictionary, or production-audio file is modified by either
command.
