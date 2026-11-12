# Data analysis

## Sets

### DEV: 65 dialogues

| | min | median | mean | max |
|---|---|---|---|---|
| messages | 11 | 14 | 19.5 | 115 |
| characters | 769 | 990 | 1293 | 5089 |

Language / channel: EN agent chat: 15, KZ agent chat: 15, RU agent chat: 30, RU voice call: 5

Messages by speaker: client 505 (40%), operator 339 (27%), bot 315 (25%), system 109 (9%)
; empty messages: 0.

### TEST: 13 dialogues

| | min | median | mean | max |
|---|---|---|---|---|
| messages | 11 | 16 | 16.5 | 26 |
| characters | 724 | 1180 | 1233 | 1843 |

Language / channel: EN agent chat: 3, KZ agent chat: 4, RU agent chat: 4, RU voice call: 2

Messages by speaker: client 75 (35%), bot 61 (28%), operator 50 (23%), system 29 (13%)
; empty messages: 0.

## Label balance

### TEST (external annotator): 13 dialogues

| Criterion | answers |
|---|---|
| c1 | no: 2, yes: 11 |
| c2 | na: 4, no: 2, yes: 7 |
| c3 | na: 9, no: 1, yes: 3 |
| c4 | 0: 2, 15: 1, 20: 9, na: 1 |
| c5 | no: 3, yes: 10 |
| c6 | 10: 8, 4: 3, 7: 2 |
| c7 | na: 2, no: 4, yes: 7 |
| c8 | no: 12, yes: 1 |

N/A labels: 16 of 104 (15%).

### DEV-19 (team): 19 dialogues

| Criterion | answers |
|---|---|
| c1 | no: 2, yes: 17 |
| c2 | na: 9, no: 6, yes: 4 |
| c3 | na: 13, no: 3, yes: 3 |
| c4 | 0: 2, 10: 2, 15: 1, 20: 13, na: 1 |
| c5 | no: 5, yes: 14 |
| c6 | 10: 11, 4: 6, 7: 2 |
| c7 | na: 4, no: 11, yes: 4 |
| c8 | no: 14, yes: 5 |

N/A labels: 27 of 152 (18%).

## Overlap between DEV and TEST

### all messages

DEV to nearest other DEV dialogue (reference): median 0.426, 90th percentile 0.480, max 0.504.

| TEST dialogue | nearest DEV dialogue | Jaccard (word 3-grams) |
|---|---|---|
| t-ru-01 | p1-ru-025 | 0.288 |
| t-ru-02 | p1-ru-025 | 0.359 |
| t-ru-03 | p1-ru-025 | 0.271 |
| t-ru-04 | p1-ru-025 | 0.401 |
| t-ru-05 | p4-ru-003 | 0.079 |
| t-ru-06 | p4-ru-001 | 0.080 |
| t-kz-01 | p1-kz-014 | 0.393 |
| t-kz-02 | p1-kz-014 | 0.316 |
| t-kz-03 | p1-kz-014 | 0.386 |
| t-kz-04 | p1-kz-014 | 0.382 |
| t-en-01 | p1-en-011 | 0.358 |
| t-en-02 | p1-en-011 | 0.414 |
| t-en-03 | p1-en-011 | 0.556 |

TEST dialogues more similar to DEV than any DEV dialogue is to another: ['t-en-03'].

### client and operator messages only

DEV to nearest other DEV dialogue (reference): median 0.030, 90th percentile 0.061, max 0.076.

| TEST dialogue | nearest DEV dialogue | Jaccard (word 3-grams) |
|---|---|---|
| t-ru-01 | p1-ru-006 | 0.014 |
| t-ru-02 | p1-ru-012 | 0.008 |
| t-ru-03 | p1-ru-015 | 0.019 |
| t-ru-04 | p4-ru-004 | 0.001 |
| t-ru-05 | p4-ru-003 | 0.011 |
| t-ru-06 | p4-ru-001 | 0.004 |
| t-kz-01 | p1-ru-025 | 0.013 |
| t-kz-02 | p1-kz-006 | 0.015 |
| t-kz-03 | p1-kz-001 | 0.022 |
| t-kz-04 | p1-kz-006 | 0.021 |
| t-en-01 | p1-en-012 | 0.013 |
| t-en-02 | p1-en-003 | 0.042 |
| t-en-03 | p1-en-009 | 0.030 |

TEST dialogues more similar to DEV than any DEV dialogue is to another: none.

### Identical client/operator messages (longer than 40 characters)

none

Shared conversation IDs: none.

