# Experiment results

Test set: 13 dialogs, 104 labels.

| Tag | System | Runs | T | Accuracy | 95% CI (run 0) | Score MAE | s/dialog | calls | tokens in/out | memory GB (GPU) | flip rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main | pipeline | 1 | 0.0 | 85.6% | [76.9%, 93.3%] | 11.0 | 34.7 | 17.4 | 13032/1044 | 6.28 (5.49) |  |
| main | single_prompt | 1 | 0.0 | 69.2% | [59.6%, 77.9%] | 12.1 | 14.3 | 1.0 | 1779/467 | 6.28 (5.49) |  |

## Per criterion (run 0)

| Tag | System | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 |
|---|---|---|---|---|---|---|---|---|---|
| main | pipeline | 13/13 | 7/13 | 11/13 | 11/13 | 12/13 | 10/13 | 13/13 | 12/13 |
| main | single_prompt | 12/13 | 6/13 | 12/13 | 1/13 | 11/13 | 8/13 | 9/13 | 13/13 |

## Per language (run 0)

- main / pipeline: EN 21/24 (88%), KZ 29/32 (91%), RU 39/48 (81%)
- main / single_prompt: EN 14/24 (58%), KZ 21/32 (66%), RU 37/48 (77%)

## Gross violation flag c8 (run 0)

- main / pipeline: {'tp': 1, 'fp': 1, 'fn': 0}
- main / single_prompt: {'tp': 1, 'fp': 0, 'fn': 0}

## Errors: expected -> predicted (run 0)

- main / pipeline: {"c2": {"na->no": 2, "yes->na": 1, "no->na": 2, "yes->no": 1}, "c3": {"no->na": 1, "na->no": 1}, "c4": {"20->15": 1, "0->10": 1}, "c5": {"no->yes": 1}, "c6": {"7->10": 2, "10->4": 1}, "c8": {"no->yes": 1}}
- main / single_prompt: {"c1": {"no->yes": 1}, "c2": {"no->na": 1, "yes->na": 3, "na->yes": 2, "no->yes": 1}, "c3": {"no->na": 1}, "c4": {"20->na": 9, "0->na": 2, "15->na": 1}, "c5": {"yes->no": 1, "no->yes": 1}, "c6": {"7->10": 2, "10->7": 1, "4->7": 1, "4->10": 1}, "c7": {"no->na": 2, "no->yes": 2}}

## Paired comparisons (run 0, same dialogs)

- main: pipeline - single_prompt = +16.3%, 95% CI [+5.8%, +26.9%], P(diff > 0) = 1.00

## Pipeline disagreements with the labels (run 0 of each tag)

- [main] t-ru-01 (RU) c2: label na, predicted no. Выявление потребности — Нет. Данных для ответа не хватало, но оператор ничего не уточнил. Основание — реплики оператора #10, #13. Проверен участок #10–#17.
- [main] t-ru-02 (RU) c2: label yes, predicted na. Выявление потребности — N/A. Данных для ответа хватало с самого начала. Основание — реплика клиента #1.
- [main] t-ru-02 (RU) c3: label no, predicted na. Идентификация — N/A. Запрос не требовал идентификации.
- [main] t-ru-02 (RU) c4: label 20, predicted 15. Корректная и полная консультация — 15 из 20. Основной вопрос решён, пропущена второстепенная деталь. Основание — реплика клиента #13, реплика оператора #14.
- [main] t-ru-02 (RU) c8: label no, predicted yes. Грубые ошибки — Да. Выявлено: раскрытие конфиденциальной информации. Основание — реплика оператора #12.
- [main] t-ru-04 (RU) c2: label no, predicted na. Выявление потребности — N/A. Данных для ответа хватало с самого начала. Основание — реплика клиента #1.
- [main] t-ru-04 (RU) c4: label 0, predicted 10. Корректная и полная консультация — 10 из 20. Часть запроса закрыта, существенный вопрос остался открытым. Основание — реплики клиента #1, #13.
- [main] t-ru-06 (RU) c3: label na, predicted no. Идентификация — Нет. Требовалась проверка личности, но оператор её не провёл. Основание — реплика оператора #17. Проверен участок #17–#22.
- [main] t-ru-06 (RU) c6: label 7, predicted 10. Управление диалогом — 10 из 10. Ответы ясные и связные; при явном ожидании оператор предупредил. Основание — реплика оператора #11.
- [main] t-kz-02 (KZ) c6: label 7, predicted 10. Диалогты басқару — 10 ішінен 10. Жауаптар анық және байланысты; айқын күту болса, оператор ескертті. Негіз — оператор репликасы #10.
- [main] t-kz-03 (KZ) c2: label na, predicted no. Қажеттілікті анықтау — Жоқ. Жауап беру үшін деректер жеткіліксіз болды, бірақ оператор ештеңе нақтыламады. Негіз — оператор репликасы #10. Тексерілген бөлік: #1
- [main] t-kz-03 (KZ) c6: label 10, predicted 4. Диалогты басқару — 10 ішінен 4. Тұжырымдар немесе жауаптардың реті салдарынан клиент қайта сұрауға мәжбүр. Негіз — клиент репликасы #11. Тексерілген бөлік: #11–
- [main] t-en-02 (EN) c2: label no, predicted na. Needs discovery — N/A. The information needed to answer was available from the start. Basis — client message #1.
- [main] t-en-02 (EN) c5: label no, predicted yes. Empathy and customer focus — Yes. The operator was polite and addressed the specific problem the client complained about. Basis — operator message #12, client m
- [main] t-en-03 (EN) c2: label yes, predicted no. Needs discovery — No. The information was not enough to answer, but the operator did not clarify anything. Basis — operator message #10. Checked: #10–#11.
