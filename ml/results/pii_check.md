# Personal-data masking check

| # | input | masked | expected | result |
|---|---|---|---|---|
| 1 | Мой ИИН 900101300123, проверьте пожалуйста | Мой ИИН [IIN], проверьте пожалуйста | iin | ok |
| 2 | ЖСН: 851231400567 | ЖСН: [IIN] | iin | ok |
| 3 | My national ID is 020304500789. | My national ID is [IIN]. | iin | ok |
| 4 | Карта 4400 4301 2345 6789 не проходит | Карта [CARD] не проходит | card | ok |
| 5 | card 5169-4931-0012-3456 was blocked | card [CARD] was blocked | card | ok |
| 6 | Картам 4400430123456789 | Картам [CARD] | card | ok |
| 7 | Переведите на KZ12722C000012345678 | Переведите на [IBAN] | iban | ok |
| 8 | IBAN kz86125KZT5004100100 please | IBAN [IBAN] please | iban | ok |
| 9 | Позвоните мне +7 701 234 56 78 | Позвоните мне [PHONE] | phone | ok |
| 10 | тел. 8 (747) 123-45-67 | тел. [PHONE] | phone | ok |
| 11 | Нөмірім +77012345678 | Нөмірім [PHONE] | phone | ok |
| 12 | Call me at +44 20 7946 0958 | Call me at +44 20 7946 0958 | phone | WRONG |
| 13 | Почта ivanov.a@mail.kz | Почта [EMAIL] | email | ok |
| 14 | my email is john_doe+test@gmail.com | my email is [EMAIL] | email | ok |
| 15 | ИИН 900101300123, тел +7 701 234 56 78, почта a@b.kz | ИИН [IIN], тел [PHONE], почта [EMAIL] | email, iin, phone | ok |
| 16 | Сумма вывода 1 500 000 тенге | Сумма вывода 1 500 000 тенге | — | ok |
| 17 | Заявка №48213 от 12.03.2025 в 14:35 | Заявка №48213 от 12.03.2025 в 14:35 | — | ok |
| 18 | Order 20250312 was executed at 187.45 USD | Order 20250312 was executed at 187.45 USD | — | ok |
| 19 | Купил 300 акций AAPL по 172,5 | Купил 300 акций AAPL по 172,5 | — | ok |
| 20 | Счёт брокерский 12345678 | Счёт брокерский 12345678 | — | ok |
| 21 | Комиссия 0,25% но не менее 1 000 тг | Комиссия 0,25% но не менее 1 000 тг | — | ok |
| 22 | Тикер KZTO, ISIN KZ1C00000876 | Тикер KZTO, ISIN KZ1C00000876 | — | ok |
| 23 | Код подтверждения 482913 | Код подтверждения 482913 | — | ok |
| 24 | Дивиденды за 2024 год: 2 450,75 тенге | Дивиденды за 2024 год: 2 450,75 тенге | — | ok |

| type | masked (of expected) | false alarms |
|---|---|---|
| card | 3/3 | 0 |
| email | 3/3 | 0 |
| iban | 2/2 | 0 |
| iin | 4/4 | 0 |
| phone | 4/5 | 0 |

On DEV (65 dialogues, 1268 messages) the rules fired: never.
