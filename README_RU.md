# JSON Schema Generator

Python-утилита для генерации **максимально заполненного JSON-экземпляра** из JSON Schema.

## Возможности

- ✅ **Все поля включены** — как обязательные, так и опциональные свойства
- ✅ **Строки максимальной длины** — заполняет строки до лимита `maxLength` (по умолчанию: 100 символов)
- ✅ **Поддержка паттернов** — генерирует строки по regex из `pattern` (использует `rstr`, если установлен)
- ✅ **Все форматы** — `date-time`, `date`, `time`, `email`, `uri`, `uuid`, `ipv4`, `ipv6`, `hostname`
- ✅ **Enum → самое длинное значение**
- ✅ **Максимальные числа** — использует `maximum`, `exclusiveMaximum` или 999999999
- ✅ **Поддержка `multipleOf`**
- ✅ **Массивы** — заполняет до `maxItems` (по умолчанию: 5 элементов)
- ✅ **Разрешение `$ref`** — поддерживает `$defs` и `definitions`
- ✅ **Комбинеры** — `allOf`, `anyOf`, `oneOf`
- ✅ **`additionalProperties`** — добавляет 3 дополнительных максимально заполненных поля
- ✅ **Без внешних зависимостей** — только стандартная библиотека (опционально `rstr` для генерации по паттернам)

## Установка

```bash
# Зависимости не требуются — только Python 3.7+
git clone https://github.com/vkrasnovid/json-schema-generator
cd json-schema-generator

# Опционально: установите rstr для улучшенной генерации строк по паттернам
pip install rstr
```

## Использование

### Из файла со схемой

```bash
python3 json_schema_generator.py schema.json
```

### Из встроенной схемы

```bash
python3 json_schema_generator.py --schema '{"type":"object","properties":{"name":{"type":"string","maxLength":50}}}'
```

### Запись в файл

```bash
python3 json_schema_generator.py schema.json -o output.json
python3 json_schema_generator.py schema.json --output result.json --indent 4
```

### Параметры командной строки

```
usage: json_schema_generator.py [-h] [--schema SCHEMA] [--output OUTPUT] [--indent INDENT] [schema_file]

позиционные аргументы:
  schema_file           Путь к файлу JSON Schema

опции:
  --schema SCHEMA       Строка со схемой (inline)
  --output, -o OUTPUT   Файл для вывода (по умолчанию: stdout)
  --indent INDENT       Уровень отступа JSON (по умолчанию: 2)
```

## Примеры

### Входная схема

```json
{
  "type": "object",
  "properties": {
    "id":       { "type": "integer", "maximum": 2147483647 },
    "username": { "type": "string", "maxLength": 32, "pattern": "^[a-zA-Z0-9_]+$" },
    "email":    { "type": "string", "format": "email", "maxLength": 255 },
    "bio":      { "type": "string", "maxLength": 500 },
    "verified": { "type": "boolean" },
    "tags": {
      "type": "array",
      "maxItems": 5,
      "items": { "type": "string", "maxLength": 20 }
    }
  }
}
```

### Сгенерированный результат

```json
{
  "id": 2147483647,
  "username": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "email": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@example.com",
  "bio": "xxxx...xxxx (500 символов)",
  "verified": true,
  "tags": [
    "xxxxxxxxxxxxxxxxxxxx",
    "xxxxxxxxxxxxxxxxxxxx",
    "xxxxxxxxxxxxxxxxxxxx",
    "xxxxxxxxxxxxxxxxxxxx",
    "xxxxxxxxxxxxxxxxxxxx"
  ]
}
```

## Правила генерации строк

| Ограничение | Поведение |
|-------------|-----------|
| `maxLength` | Заполняется точно до maxLength |
| Только `minLength` | Использует `max(minLength * 3, 100)`, максимум 1000 |
| `pattern` | Соответствует паттерну, заполняется до maxLength (использует `rstr`, если установлен) |
| `enum` | Выбирает самое длинное значение |
| `format: date-time` | `"2099-12-31T23:59:59.999999Z"` |
| `format: date` | `"2099-12-31"` |
| `format: uuid` | `"ffffffff-ffff-4fff-bfff-ffffffffffff"` |
| `format: email` | Дополняет локальную часть до maxLength |
| `format: uri` | Дополняет путь до maxLength |
| `format: ipv4` | `"255.255.255.255"` |
| `format: ipv6` | `"ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"` |
| не задано | 100 символов `x` |

## Правила генерации чисел

| Ограничение | Поведение |
|-------------|-----------|
| `maximum` | Использует maximum |
| `exclusiveMaximum` | Использует `maximum - 1` (int) или `maximum - 0.001` (float) |
| `minimum` | Использует `minimum * 1000` или 999999999 |
| не задано | 999999999 (int) или 999999999.999999 (float) |
| `multipleOf` | Округляет вниз до ближайшего кратного |

## Запуск тестов

```bash
python3 test_generator.py
```

43 теста: плоские объекты, вложенные объекты, массивы, паттерны, `$ref`, комбинеры (`allOf`/`anyOf`/`oneOf`), все форматы, граничные случаи.

## Сценарии использования

- Тестирование API-эндпоинтов с максимально нагруженными данными
- Проверка ограничений длины полей на бэкенде
- Нагрузочное тестирование с реалистичными граничными данными
- Генерация примеров для документации схемы

## Лицензия

MIT
