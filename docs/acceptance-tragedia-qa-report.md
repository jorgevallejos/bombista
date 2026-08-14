# QA report — Tragedia de cerdo asado

- Song file: `/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json`
- Audio file: `runs/tragedia-2026-07-03/tragedia-master-16k.wav`
- Model: faster-whisper `medium` (lang `es`)
- Generated: 2026-07-03T11:22:38
- Re-run (skips transcription): `bombista extract runs/tragedia-2026-07-03/tragedia-master-16k.wav /Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json -o runs/tragedia-2026-07-03 --words runs/tragedia-2026-07-03/asr-words.jsonl --lang es`
- Bands: HIGH 28 / REVIEW 1 / FAIL 0

> Timeline times are only meaningful relative to the audio you feed in. For Video-mode songs, extract the audio from the linked animation video (`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`); for Auto-mode songs, use the master recording.

## Needs attention

| line | band | canonical text | ASR context | start | end | dur | signals |
|------|------|----------------|-------------|-------|-----|-----|---------|
| 21 | REVIEW | ¡Qué suerte divina! ¡Me voy a escapar! | que quedó medio abierta Que suerte divina, me | 95.74 | 102.60 | 6.86 | ambiguous |

- Line 21: re-run `extract` with `--anchor 21=<seconds>` and `--words runs/tragedia-2026-07-03/asr-words.jsonl` to skip re-transcription (candidate start was 95.74 s).

## All lines

| line | band | canonical text | ASR context | start | end | dur | signals |
|------|------|----------------|-------------|-------|-----|-----|---------|
| 0 | HIGH | Me acuestan en la cama |  | 0.96 | 3.76 | 2.80 | override |
| 1 | HIGH | de plata brillante. | de plata brillante Me ungen con hierbas, manteca, | 3.76 | 8.00 | 4.24 | clean-anchor |
| 2 | HIGH | Me ungen con hierbas, | Me ungen con hierbas, manteca, ajo y sal | 8.00 | 12.04 | 4.04 | clean-anchor |
| 3 | HIGH | manteca, ajo y sal. | manteca, ajo y sal Mi piel como cristal | 12.04 | 15.90 | 3.86 | clean-anchor |
| 4 | HIGH | Mi piel como cristal, | Mi piel como cristal El chef me admira | 15.90 | 19.72 | 3.82 | clean-anchor |
| 5 | HIGH | El chef me admira como arte. | El chef me admira como arete Una locura | 19.72 | 23.24 | 3.52 | clean-anchor |
| 6 | HIGH | "Una delicia serás", suspira, ⏎ mientras yo piens… | Una locura será suspira mientras yo pienso en | 23.24 | 30.46 | 7.22 | clean-anchor |
| 7 | HIGH | Soy la estrella de un festín infernal. | Soy la estrella de un festín infernal Me | 30.46 | 38.24 | 7.78 | clean-anchor |
| 8 | HIGH | Me alzan en brazos | Me alzan en brazos como a rey de | 38.24 | 42.04 | 3.80 | clean-anchor |
| 9 | HIGH | como al rey de Roma. | como a rey de Roma Una manzana en | 42.04 | 45.62 | 3.58 | clean-anchor |
| 10 | HIGH | Una manzana en mi boca, | Una manzana en mi boca para que luzca | 45.62 | 48.14 | 2.52 | clean-anchor |
| 11 | HIGH | para que luzca feliz. | para que luzca feliz Esliza en mi cuerpo, | 48.14 | 55.20 | 7.06 | clean-anchor |
| 12 | HIGH | Deslizan mi cuerpo, | Esliza en mi cuerpo, hace calor al diente | 55.20 | 58.50 | 3.30 | clean-anchor |
| 13 | HIGH | hacia el fuego ardiente. |  | 58.50 | 62.16 | 3.66 | override |
| 14 | HIGH | El aire me envuelve de humo y calor, ⏎ y yo canto… | El aire me enunda de lujo y calor | 62.16 | 68.80 | 6.64 | clean-anchor |
| 15 | HIGH | Soy la estrella de un festín mortal. | Soy la estrella de un festín mortal Que | 68.80 | 72.92 | 4.12 | clean-anchor |
| 16 | HIGH | ¡Qué honor divino! Menú infernal! | Que honor divino, menú infernal Yo desde las | 72.92 | 76.60 | 3.68 | clean-anchor |
| 17 | HIGH | Yo entre las brasas sonrío al destino. | Yo desde las brazas sonrío al destino Oh, | 76.60 | 83.84 | 7.24 | clean-anchor |
| 18 | HIGH | Oh, Un corte de luz, | Oh, un corte de luz, bendita sorpresa La | 83.84 | 88.74 | 4.90 | clean-anchor |
| 19 | HIGH | ¡Bendita sorpresa! | bendita sorpresa La cocina revuelta y la puerta | 88.74 | 91.48 | 2.74 | clean-anchor |
| 20 | HIGH | La cocina revuelta y la puerta del horno, ⏎ que q… | La cocina revuelta y la puerta del horno | 91.48 | 95.74 | 4.26 | clean-anchor |
| 21 | REVIEW | ¡Qué suerte divina! ¡Me voy a escapar! | que quedó medio abierta Que suerte divina, me | 95.74 | 102.60 | 6.86 | ambiguous |
| 22 | HIGH | Salto ya del horno, listo pa' volar. | Salto ya del horno, listo pa' volar al | 102.60 | 106.40 | 3.80 | clean-anchor |
| 23 | HIGH | Al bosque me voy, crujiente y triunfante. | al bosque me voy Su gente y tu | 106.40 | 112.22 | 5.82 | clean-anchor |
| 24 | HIGH | Respiro libre, siento la brisa, ⏎ me fui del infi… | Respiro libre, siento la brisa Me fui del | 112.22 | 120.44 | 8.22 | clean-anchor |
| 25 | HIGH | Pero en la sombra colmillos de plata, ⏎ un lobo e… | Pero en la sombra colmillos de plata Un | 120.44 | 127.96 | 7.52 | clean-anchor |
| 26 | HIGH | Soy la estrella de un festín mortal. | Soy la estrella de un festín mortal Que | 127.96 | 132.00 | 4.04 | clean-anchor |
| 27 | HIGH | ¡Qué honor divino! Menú infernal! | Que honor divino, menú infernal Yo desde las | 132.00 | 136.16 | 4.16 | clean-anchor |
| 28 | HIGH | Desde las entrañas sonrío al destino. | desde las tripas sonrío al destino Oh, un | 136.16 | 160.48 | 24.32 | clean-anchor |
