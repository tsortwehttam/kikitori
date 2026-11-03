# Kikitori 聞き取り

A private Japanese listening podcast built from my Anki cards. Each daily episode runs about 30 minutes and mixes:

1. **Card sentences** from recently added and production cards: Japanese, English, then Japanese again, with a soft chime between cards.
2. **News**: real stories from the last day or two, rewritten as N2-level broadcast Japanese.
3. **A JLPT-style dialogue** between a man and a woman, followed by spoken multiple-choice questions and answers.
4. **An opinion column** on a current topic.
5. **A translated essay**: something I'd otherwise read in English, condensed into Japanese.

Each segment's writer is asked to work in vocabulary I'm currently learning in Anki.

## How it works

- `cards.py` syncs Anki through AnkiConnect and exports the card sentences added or reviewed since the last episode (`build/cards-today.json`), plus the vocabulary the segments should use (`build/vocab.txt`).
- The segments are written by Claude Code: news, an opinion column, and a translated essay by subagents, and the dialogue as a spec that `dialogue.py` expands into `build/seg-dialogue.json`.
- `episode.py` assembles the day's script from the segment files (`build/seg-*.json`) and the card list, and records the episode's topics in `build/history.jsonl` so later episodes don't repeat them.
- `build.py` renders a script to MP3. Japanese uses [AivisSpeech](https://aivis-project.com) running locally (花音, わかな, 阿井田 茂; started automatically if it isn't running) or Amazon Polly. English uses macOS `say`. Audio is loudness-normalised to podcast level.
- `publish.py` uploads the episode to S3 and rebuilds an RSS feed. CloudFront serves the feed under a secret path, and podcast apps subscribe to it by URL. `--remove` deletes an episode.
- `Infra/template.yaml` is the CloudFormation stack: a private S3 bucket behind CloudFront.

Configuration lives in `.env`, which is not committed: `FEED_PREFIX` is the secret path segment of the feed URL. Generated episodes (`build/`, `scripts/episode-*.json`) aren't committed either, because they contain rewritten news and translated third-party writing.

## Setup

```sh
aws --profile new-account --region us-east-1 cloudformation deploy --stack-name kikitori --template-file Infra/template.yaml
echo "FEED_PREFIX=$(python3 -c 'import secrets; print(secrets.token_hex(12))')" > .env
~/Applications/AivisSpeech-Engine/macOS-arm64/run --port 10101 &   # AivisSpeech Engine
python3 build.py scripts/sample.json --engine aivis
python3 publish.py build/sample-aivis.mp3 --script scripts/sample.json --title "Sample"
```

Requires Python 3, ffmpeg, the AWS CLI, and macOS for `say`.
