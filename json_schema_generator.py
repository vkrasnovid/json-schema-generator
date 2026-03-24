"""
JSON Schema Generator — generates a maximally-filled JSON instance from a JSON Schema.

Features:
- All fields included (required + optional)
- Strings padded to maxLength (default 100 chars)
- Pattern strings: uses rstr if available, else repeats filling
- Enum → longest value
- All common formats supported
- Numbers → maximum allowed value
- Arrays → maxItems items (or 5 by default)
- $ref resolution (supports $defs and definitions)
- allOf / anyOf / oneOf support
"""

import json
import re
import sys
import argparse
from typing import Any, Dict, Optional

# Try to import rstr for pattern generation
try:
    import rstr
    HAS_RSTR = True
except ImportError:
    HAS_RSTR = False


DEFAULT_STRING_LENGTH = 100
DEFAULT_ARRAY_ITEMS = 5
MAX_ARRAY_ITEMS = 20
MAX_STRING_LENGTH = 10000


def resolve_ref(ref: str, root_schema: dict) -> dict:
    """Resolve a $ref within the root schema."""
    if not ref.startswith("#"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node = root_schema
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {}
    return node if isinstance(node, dict) else {}


def merge_schemas(*schemas) -> dict:
    """Merge multiple schemas together (best-effort)."""
    merged = {}
    for schema in schemas:
        if not isinstance(schema, dict):
            continue
        for key, value in schema.items():
            if key == "properties" and "properties" in merged:
                merged["properties"] = {**merged["properties"], **value}
            elif key == "required" and "required" in merged:
                merged["required"] = list(set(merged["required"]) | set(value))
            elif key not in merged:
                merged[key] = value
    return merged


def generate_string(schema: dict, root_schema: dict) -> str:
    """Generate a maximum-length string matching the schema."""
    fmt = schema.get("format")
    enum = schema.get("enum")
    pattern = schema.get("pattern")
    max_len = schema.get("maxLength")
    min_len = schema.get("minLength", 0)

    # Enum → pick longest
    if enum:
        str_values = [str(v) for v in enum if isinstance(v, str)]
        if str_values:
            return max(str_values, key=len)

    # Format-specific values
    if fmt:
        if fmt == "date-time":
            val = "2099-12-31T23:59:59.999999Z"
        elif fmt == "date":
            val = "2099-12-31"
        elif fmt == "time":
            val = "23:59:59.999999Z"
        elif fmt == "uuid":
            val = "ffffffff-ffff-4fff-bfff-ffffffffffff"
        elif fmt == "ipv4":
            val = "255.255.255.255"
        elif fmt == "ipv6":
            val = "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
        elif fmt == "email":
            target = max_len or DEFAULT_STRING_LENGTH
            domain = "@example.com"
            local_len = max(1, target - len(domain))
            val = ("x" * local_len) + domain
            val = val[:target]
        elif fmt == "uri":
            target = max_len or DEFAULT_STRING_LENGTH
            prefix = "https://example.com/"
            pad_len = max(0, target - len(prefix))
            val = prefix + ("x" * pad_len)
            val = val[:target]
        elif fmt == "hostname":
            target = max_len or DEFAULT_STRING_LENGTH
            val = ("x" * target)
        else:
            target = max_len or DEFAULT_STRING_LENGTH
            val = "x" * target
        # Respect maxLength
        if max_len:
            val = val[:max_len]
        return val

    # Pattern-based generation
    if pattern:
        target_len = max_len or DEFAULT_STRING_LENGTH
        # Always use the smart fallback parser — it respects structure,
        # quantifiers, literal separators, and ensures full character diversity.
        # rstr.xeger() generates random-length strings with random char selection,
        # which misses the "maximally filled" goal.
        val = _fill_pattern_fallback(pattern, target_len)
        return val[:target_len]

    # Plain string: fill to maxLength
    if max_len:
        return "x" * max_len
    elif min_len:
        length = min(max(min_len * 3, DEFAULT_STRING_LENGTH), MAX_STRING_LENGTH)
        return "x" * length
    else:
        return "x" * DEFAULT_STRING_LENGTH


def _expand_char_class(class_body: str) -> list:
    """
    Expand a character class body (the content between [ and ]) into a list
    of individual characters.  Handles ranges (a-z, 0-9, а-я, etc.),
    escape sequences (\\d, \\w, \\s), and literal characters.
    """
    chars: list[str] = []
    i = 0
    n = len(class_body)
    # Skip leading ^ (negated class — we can't invert, just use printable)
    if i < n and class_body[i] == '^':
        import string
        return list(string.printable.strip())

    while i < n:
        # Escape sequences
        if class_body[i] == '\\' and i + 1 < n:
            nc = class_body[i + 1]
            if nc == 'd':
                chars.extend('0123456789')
            elif nc == 'w':
                chars.extend(
                    list('abcdefghijklmnopqrstuvwxyz')
                    + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
                    + list('0123456789')
                    + ['_']
                )
            elif nc == 's':
                chars.append(' ')
            elif nc == 'n':
                chars.append('\n')
            elif nc == 't':
                chars.append('\t')
            else:
                # Escaped literal (e.g. \\-, \\., \\\\)
                chars.append(nc)
            i += 2
            continue

        # Check for range: c - d
        if i + 2 < n and class_body[i + 1] == '-' and class_body[i + 2] != ']':
            start_char = class_body[i]
            end_char = class_body[i + 2]
            lo, hi = ord(start_char), ord(end_char)
            if lo <= hi:
                chars.extend(chr(c) for c in range(lo, hi + 1))
            i += 3
            continue

        # Literal character (including '-' at start/end of class)
        chars.append(class_body[i])
        i += 1

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for c in chars:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _parse_pattern_tokens(pattern: str) -> list:
    """
    Parse a regex pattern into a list of tokens.
    Each token is a tuple: ('literal', char), ('class', [chars]), or ('dot',).
    Anchors (^ $) are skipped.  Quantifiers are attached to the preceding token
    as a repeat count (min, max).
    Returns list of (token, repeat_min, repeat_max).
    """
    tokens: list[tuple] = []
    i = 0
    n = len(pattern)

    while i < n:
        c = pattern[i]

        # Skip anchors
        if c in ('^', '$'):
            i += 1
            continue

        # Character class [...]
        if c == '[':
            j = i + 1
            # Handle ] as first char in class
            if j < n and pattern[j] == ']':
                j += 1
            while j < n and pattern[j] != ']':
                if pattern[j] == '\\' and j + 1 < n:
                    j += 2
                else:
                    j += 1
            class_body = pattern[i + 1:j]
            chars = _expand_char_class(class_body)
            token = ('class', chars)
            i = j + 1  # skip past ]

        # Escape sequences outside class
        elif c == '\\' and i + 1 < n:
            nc = pattern[i + 1]
            if nc == 'd':
                token = ('class', list('0123456789'))
            elif nc == 'w':
                token = ('class', list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'))
            elif nc == 's':
                token = ('class', [' '])
            else:
                token = ('literal', nc)
            i += 2

        # Dot — any printable
        elif c == '.':
            import string
            token = ('class', list(string.printable.strip()))
            i += 1

        # Grouping — skip parens (flatten)
        elif c in ('(', ')'):
            i += 1
            continue

        # Alternation — stop (just use left branch)
        elif c == '|':
            break

        # Quantifiers — attach to previous token
        elif c in ('{', '*', '+', '?'):
            if c == '{':
                j = i + 1
                while j < n and pattern[j] != '}':
                    j += 1
                quant_body = pattern[i + 1:j]
                i = j + 1
                if ',' in quant_body:
                    parts = quant_body.split(',', 1)
                    rmin = int(parts[0]) if parts[0].strip() else 0
                    rmax = int(parts[1]) if parts[1].strip() else max(rmin, 50)
                else:
                    rmin = rmax = int(quant_body)
                if tokens:
                    prev_tok, _, _ = tokens[-1]
                    tokens[-1] = (prev_tok, rmin, rmax)
                continue
            elif c == '*':
                if tokens:
                    prev_tok, _, _ = tokens[-1]
                    tokens[-1] = (prev_tok, 0, 50)
                i += 1
                continue
            elif c == '+':
                if tokens:
                    prev_tok, _, _ = tokens[-1]
                    tokens[-1] = (prev_tok, 1, 50)
                i += 1
                continue
            elif c == '?':
                if tokens:
                    prev_tok, _, _ = tokens[-1]
                    tokens[-1] = (prev_tok, 0, 1)
                i += 1
                continue
        else:
            # Literal character
            token = ('literal', c)
            i += 1

        # Default repeat: exactly 1
        tokens.append((token, 1, 1))

    return tokens


def _fill_pattern_fallback(pattern: str, target_len: int) -> str:
    """
    Smart pattern filling fallback (no rstr).
    Parses the regex structure and generates a string that respects:
    - Literal characters between groups
    - Character classes with full expansion and diversity
    - Quantifiers {n}, {n,m}, +, *, ?
    """
    tokens = _parse_pattern_tokens(pattern)

    if not tokens:
        return 'x' * target_len

    parts: list[str] = []
    for token, rmin, rmax in tokens:
        kind = token[0]
        count = rmax  # use max to fill maximally

        if kind == 'literal':
            ch = token[1]
            parts.append(ch * count)
        elif kind == 'class':
            char_list = token[1]
            if not char_list:
                char_list = ['x']
            # Build segment ensuring we cycle through ALL chars for max diversity.
            # If count < len(char_list), we need to use a stride to cover all groups.
            L = len(char_list)
            segment = []
            if L <= 1:
                segment = char_list * count
            elif count >= L:
                # More slots than chars: cycle through all
                for idx in range(count):
                    segment.append(char_list[idx % L])
            else:
                # Fewer slots than chars: reserve space for tail, then stride
                # through middle chars to cover all groups (digits, latin, cyrillic, etc)
                tail_count = min(3, count // 4)  # reserve ~25% of slots for tail
                main_count = count - tail_count
                
                stride = max(1, (L - tail_count) // main_count) if main_count > 0 else 1
                for idx in range(main_count):
                    pos = min(idx * stride, L - tail_count - 1)
                    segment.append(char_list[pos])
                
                # Add tail (last unique important chars)
                for i in range(tail_count):
                    pos = L - tail_count + i
                    if pos < L:
                        segment.append(char_list[pos])
            parts.append(''.join(segment))

    return ''.join(parts)


def generate_number(schema: dict, is_integer: bool) -> Any:
    """Generate maximum allowed number."""
    maximum = schema.get("maximum")
    exclusive_max = schema.get("exclusiveMaximum")
    minimum = schema.get("minimum")
    multiple_of = schema.get("multipleOf")

    if maximum is not None:
        val = maximum
    elif exclusive_max is not None:
        if is_integer:
            val = int(exclusive_max) - 1
        else:
            val = exclusive_max - 0.001
    elif minimum is not None:
        val = minimum * 1000 if minimum != 0 else 999999999
    else:
        val = 999999999 if is_integer else 999999999.999999

    if is_integer:
        val = int(val)

    if multiple_of and multiple_of != 0:
        if is_integer:
            val = (int(val) // int(multiple_of)) * int(multiple_of)
        else:
            import math
            val = math.floor(val / multiple_of) * multiple_of

    return val


def generate(schema: dict, root_schema: dict = None, depth: int = 0) -> Any:
    """Generate a max-filled JSON value from a JSON Schema."""
    if root_schema is None:
        root_schema = schema

    if depth > 20:
        return None

    if not isinstance(schema, dict):
        return None

    # Resolve $ref
    if "$ref" in schema:
        resolved = resolve_ref(schema["$ref"], root_schema)
        merged = merge_schemas(resolved, {k: v for k, v in schema.items() if k != "$ref"})
        return generate(merged, root_schema, depth)

    # Handle combiners
    all_of = schema.get("allOf")
    any_of = schema.get("anyOf")
    one_of = schema.get("oneOf")

    if all_of:
        merged = merge_schemas(schema, *all_of)
        merged.pop("allOf", None)
        return generate(merged, root_schema, depth)

    if any_of:
        # Pick first, but try to merge all to get all fields
        merged = merge_schemas(schema, *any_of)
        merged.pop("anyOf", None)
        return generate(merged, root_schema, depth)

    if one_of:
        merged = merge_schemas(schema, one_of[0])
        merged.pop("oneOf", None)
        return generate(merged, root_schema, depth)

    # Determine type
    schema_type = schema.get("type")

    # Handle multiple types: pick first non-null, or null if only null
    if isinstance(schema_type, list):
        non_null = [t for t in schema_type if t != "null"]
        schema_type = non_null[0] if non_null else "null"

    # If no type but has properties → object
    if schema_type is None and "properties" in schema:
        schema_type = "object"
    # If no type but has items → array
    if schema_type is None and "items" in schema:
        schema_type = "array"

    if schema_type == "object" or schema_type is None:
        return generate_object(schema, root_schema, depth)
    elif schema_type == "array":
        return generate_array(schema, root_schema, depth)
    elif schema_type == "string":
        return generate_string(schema, root_schema)
    elif schema_type == "integer":
        return generate_number(schema, is_integer=True)
    elif schema_type == "number":
        return generate_number(schema, is_integer=False)
    elif schema_type == "boolean":
        return True
    elif schema_type == "null":
        return None
    else:
        return generate_string(schema, root_schema)


def generate_object(schema: dict, root_schema: dict, depth: int) -> dict:
    """Generate a max-filled object."""
    result = {}
    properties = schema.get("properties", {})

    for prop_name, prop_schema in properties.items():
        result[prop_name] = generate(prop_schema, root_schema, depth + 1)

    # Handle additionalProperties
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        for i in range(3):
            key = f"extra_field_{i+1}"
            result[key] = generate(additional, root_schema, depth + 1)

    return result


def generate_array(schema: dict, root_schema: dict, depth: int) -> list:
    """Generate a max-filled array."""
    max_items = schema.get("maxItems")
    min_items = schema.get("minItems", 0)
    items_schema = schema.get("items", {})
    prefix_items = schema.get("prefixItems", [])

    if max_items is not None:
        count = max_items
    elif min_items:
        count = min(min_items * 3, MAX_ARRAY_ITEMS)
    else:
        count = DEFAULT_ARRAY_ITEMS

    result = []

    # Handle prefixItems (tuple validation)
    for item_schema in prefix_items[:count]:
        result.append(generate(item_schema, root_schema, depth + 1))

    # Fill remaining with items schema
    remaining = count - len(result)
    if isinstance(items_schema, dict):
        for _ in range(remaining):
            result.append(generate(items_schema, root_schema, depth + 1))
    elif isinstance(items_schema, list):
        for item_schema in items_schema[:remaining]:
            result.append(generate(item_schema, root_schema, depth + 1))

    return result


def generate_from_schema(schema: dict) -> Any:
    """Public API: generate max-filled JSON from a schema dict."""
    return generate(schema, schema, 0)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a maximally-filled JSON instance from a JSON Schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python json_schema_generator.py schema.json
  python json_schema_generator.py schema.json -o output.json
  python json_schema_generator.py --schema '{"type":"object","properties":{"name":{"type":"string","maxLength":50}}}'
  python json_schema_generator.py schema.json --indent 4
        """
    )
    parser.add_argument("schema_file", nargs="?", help="Path to JSON Schema file")
    parser.add_argument("--schema", help="Inline JSON schema string")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent level (default: 2)")

    args = parser.parse_args()

    if args.schema_file and args.schema:
        parser.error("Provide either schema_file or --schema, not both")

    if args.schema_file:
        try:
            with open(args.schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except FileNotFoundError:
            print(f"Error: File not found: {args.schema_file}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in schema file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.schema:
        try:
            schema = json.loads(args.schema)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --schema: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(0)

    result = generate_from_schema(schema)
    output = json.dumps(result, indent=args.indent, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
