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
        if HAS_RSTR:
            # Try to generate a long string matching the pattern
            try:
                candidates = [rstr.xeger(pattern) for _ in range(10)]
                val = max(candidates, key=len)
                # If shorter than target, try repeating if pattern allows .* or .+
                if len(val) < target_len:
                    for _ in range(50):
                        candidate = rstr.xeger(pattern)
                        if len(candidate) > len(val):
                            val = candidate
                        if len(val) >= target_len:
                            break
                return val[:target_len]
            except Exception:
                pass
        # Fallback: try to figure out a fill character from the pattern
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


def _fill_pattern_fallback(pattern: str, target_len: int) -> str:
    """
    Basic pattern filling fallback (no rstr).
    Tries to generate a string that satisfies common patterns.
    """
    # Detect allowed characters from character classes
    char_class_match = re.search(r'\[([^\]]+)\]', pattern)
    if char_class_match:
        char_class = char_class_match.group(1)
        # Get first char that's not a range indicator
        fill_char = None
        i = 0
        while i < len(char_class):
            c = char_class[i]
            if c == '\\' and i + 1 < len(char_class):
                nc = char_class[i+1]
                if nc == 'd':
                    fill_char = '9'
                    break
                elif nc == 'w':
                    fill_char = 'x'
                    break
                elif nc == 's':
                    fill_char = ' '
                    break
                i += 2
            elif c not in '-^':
                fill_char = c
                break
            else:
                i += 1
        if fill_char:
            return fill_char * target_len

    # Check for \d
    if '\\d' in pattern:
        return '9' * target_len
    # Check for \w
    if '\\w' in pattern:
        return 'x' * target_len
    # Check for [a-z] style
    if re.search(r'[a-z]', pattern):
        return 'z' * target_len

    # Anchors only: just fill with x
    stripped = re.sub(r'[\^\$\.\*\+\?\(\)\{\}\[\]\|\\]', '', pattern)
    if stripped:
        return (stripped * (target_len // len(stripped) + 1))[:target_len]

    return 'x' * target_len


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
