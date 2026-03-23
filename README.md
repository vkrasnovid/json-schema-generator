# JSON Schema Generator

A Python utility that generates a **maximally-filled JSON instance** from a JSON Schema.

## Features

- ✅ **All fields included** — required and optional properties
- ✅ **Maximum length strings** — fills strings to their `maxLength` limit (default: 100 chars)
- ✅ **Pattern support** — generates strings matching `pattern` regex (uses `rstr` if available)
- ✅ **All formats** — `date-time`, `date`, `time`, `email`, `uri`, `uuid`, `ipv4`, `ipv6`, `hostname`
- ✅ **Enum → longest value**
- ✅ **Maximum numbers** — uses `maximum`, `exclusiveMaximum`, or 999999999
- ✅ **multipleOf** support
- ✅ **Arrays** — fills to `maxItems` (default: 5 items)
- ✅ **`$ref` resolution** — supports `$defs` and `definitions`
- ✅ **Combiners** — `allOf`, `anyOf`, `oneOf`
- ✅ **`additionalProperties`** — adds 3 extra max-filled fields
- ✅ **No external dependencies** — pure stdlib (optional `rstr` for better pattern generation)

## Installation

```bash
# No dependencies required — just Python 3.7+
git clone https://github.com/vkrasnovid/json-schema-generator
cd json-schema-generator

# Optional: install rstr for better pattern-based string generation
pip install rstr
```

## Usage

### From a schema file

```bash
python3 json_schema_generator.py schema.json
```

### From an inline schema

```bash
python3 json_schema_generator.py --schema '{"type":"object","properties":{"name":{"type":"string","maxLength":50}}}'
```

### Write to file

```bash
python3 json_schema_generator.py schema.json -o output.json
python3 json_schema_generator.py schema.json --output result.json --indent 4
```

### CLI Options

```
usage: json_schema_generator.py [-h] [--schema SCHEMA] [--output OUTPUT] [--indent INDENT] [schema_file]

positional arguments:
  schema_file           Path to JSON Schema file

options:
  --schema SCHEMA       Inline JSON schema string
  --output, -o OUTPUT   Output file (default: stdout)
  --indent INDENT       JSON indent level (default: 2)
```

## Examples

### Input schema

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

### Generated output

```json
{
  "id": 2147483647,
  "username": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "email": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@example.com",
  "bio": "xxxx...xxxx (500 chars)",
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

## String Generation Rules

| Constraint | Behavior |
|-----------|----------|
| `maxLength` | Fills exactly to maxLength |
| `minLength` only | Uses `max(minLength * 3, 100)`, capped at 1000 |
| `pattern` | Matches pattern, fills to maxLength (uses `rstr` if installed) |
| `enum` | Picks longest enum value |
| `format: date-time` | `"2099-12-31T23:59:59.999999Z"` |
| `format: date` | `"2099-12-31"` |
| `format: uuid` | `"ffffffff-ffff-4fff-bfff-ffffffffffff"` |
| `format: email` | Pads local part to maxLength |
| `format: uri` | Pads path to maxLength |
| `format: ipv4` | `"255.255.255.255"` |
| `format: ipv6` | `"ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"` |
| none | 100 `x` characters |

## Number Generation Rules

| Constraint | Behavior |
|-----------|----------|
| `maximum` | Uses maximum |
| `exclusiveMaximum` | Uses `maximum - 1` (int) or `maximum - 0.001` (float) |
| `minimum` | Uses `minimum * 1000` or 999999999 |
| none | 999999999 (int) or 999999999.999999 (float) |
| `multipleOf` | Rounds down to nearest multiple |

## Running Tests

```bash
python3 test_generator.py
```

43 tests covering: flat objects, nested objects, arrays, patterns, `$ref`, combiners (`allOf`/`anyOf`/`oneOf`), all formats, edge cases.

## Use Cases

- Testing API endpoints with maximum-load payloads
- Validating form field length limits
- Load testing with realistic edge-case data
- Schema documentation via example generation

## License

MIT
