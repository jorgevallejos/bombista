---
name: Bug report
about: Something Bombista did that it shouldn't have, or didn't do that it should
title: ''
labels: bug
assignees: ''
---

## What happened

<!-- What you expected, and what you got instead. -->

## The command

```bash
# The exact command, as pasted. Feel free to redact paths.
```

## The output

<!-- The console line (HIGH n / REVIEW n / FAIL n — …), plus any traceback. -->

## If it's a timing problem

The QA report's "Needs attention" table is the useful part — the band and
the named signals for the lines that came out wrong. Paste those rows.

- Which lines are wrong, and by roughly how much?
- What band did Bombista give them — `HIGH`, `REVIEW` or `FAIL`?
- Are they wrong by a constant offset, or does the error grow through the file?

A **constant offset** usually means the lead-in: check `leadIn.durationSec`
in the emitted timeline and whether the consumer is applying it. **Growing
error** usually means the lyrics and the audio have drifted apart — a line
inserted or removed since the alignment ran.

## Environment

- Bombista version: <!-- `bombista align --help`, or the "Tool version" line in a QA report -->
- Python version: <!-- `python -V` -->
- OS:

## Audio and lyrics

Don't attach anything you can't share — recordings and unreleased lyrics
usually fall in that category. A description of the shape is normally
enough: duration, language, number of lyric lines, and whether the audio
is the master or was extracted from a video.
