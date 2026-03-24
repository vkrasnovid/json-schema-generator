"""Tests for json_schema_generator.py"""

import json
import re
import sys
import unittest

sys.path.insert(0, ".")
from json_schema_generator import generate_from_schema


class TestFlatObject(unittest.TestCase):
    def test_all_fields_present(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 50},
                "age": {"type": "integer", "maximum": 120},
                "score": {"type": "number"},
                "active": {"type": "boolean"},
                "nothing": {"type": "null"},
            }
        }
        result = generate_from_schema(schema)
        self.assertIn("name", result)
        self.assertIn("age", result)
        self.assertIn("score", result)
        self.assertIn("active", result)
        self.assertIn("nothing", result)

    def test_string_max_length(self):
        schema = {"type": "object", "properties": {
            "code": {"type": "string", "maxLength": 20},
            "desc": {"type": "string", "maxLength": 200},
        }}
        result = generate_from_schema(schema)
        self.assertEqual(len(result["code"]), 20)
        self.assertEqual(len(result["desc"]), 200)

    def test_string_default_length(self):
        schema = {"type": "string"}
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 100)

    def test_string_min_length_only(self):
        schema = {"type": "string", "minLength": 10}
        result = generate_from_schema(schema)
        self.assertGreaterEqual(len(result), 10)

    def test_integer_maximum(self):
        schema = {"type": "integer", "maximum": 999}
        result = generate_from_schema(schema)
        self.assertEqual(result, 999)

    def test_integer_default(self):
        schema = {"type": "integer"}
        result = generate_from_schema(schema)
        self.assertEqual(result, 999999999)

    def test_number_default(self):
        schema = {"type": "number"}
        result = generate_from_schema(schema)
        self.assertAlmostEqual(result, 999999999.999999, places=3)

    def test_boolean_true(self):
        schema = {"type": "boolean"}
        result = generate_from_schema(schema)
        self.assertTrue(result)

    def test_null(self):
        schema = {"type": "null"}
        result = generate_from_schema(schema)
        self.assertIsNone(result)

    def test_enum_longest(self):
        schema = {"type": "string", "enum": ["a", "bb", "ccc", "dd"]}
        result = generate_from_schema(schema)
        self.assertEqual(result, "ccc")

    def test_multiple_of(self):
        schema = {"type": "integer", "maximum": 100, "multipleOf": 7}
        result = generate_from_schema(schema)
        self.assertEqual(result % 7, 0)
        self.assertLessEqual(result, 100)


class TestFormats(unittest.TestCase):
    def test_format_datetime(self):
        schema = {"type": "string", "format": "date-time"}
        result = generate_from_schema(schema)
        self.assertIn("T", result)
        self.assertIn("Z", result)

    def test_format_date(self):
        schema = {"type": "string", "format": "date"}
        result = generate_from_schema(schema)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2}")

    def test_format_time(self):
        schema = {"type": "string", "format": "time"}
        result = generate_from_schema(schema)
        self.assertIn(":", result)

    def test_format_uuid(self):
        schema = {"type": "string", "format": "uuid"}
        result = generate_from_schema(schema)
        self.assertRegex(result, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    def test_format_ipv4(self):
        schema = {"type": "string", "format": "ipv4"}
        result = generate_from_schema(schema)
        self.assertEqual(result, "255.255.255.255")

    def test_format_ipv6(self):
        schema = {"type": "string", "format": "ipv6"}
        result = generate_from_schema(schema)
        self.assertIn(":", result)

    def test_format_email(self):
        schema = {"type": "string", "format": "email", "maxLength": 50}
        result = generate_from_schema(schema)
        self.assertIn("@", result)
        self.assertLessEqual(len(result), 50)

    def test_format_uri(self):
        schema = {"type": "string", "format": "uri", "maxLength": 80}
        result = generate_from_schema(schema)
        self.assertTrue(result.startswith("https://"))
        self.assertLessEqual(len(result), 80)

    def test_format_uri_default_length(self):
        schema = {"type": "string", "format": "uri"}
        result = generate_from_schema(schema)
        self.assertTrue(result.startswith("https://"))
        self.assertEqual(len(result), 100)


class TestNestedObjects(unittest.TestCase):
    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "maxLength": 30},
                        "address": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string", "maxLength": 50},
                                "zip": {"type": "string", "maxLength": 10},
                            }
                        }
                    }
                }
            }
        }
        result = generate_from_schema(schema)
        self.assertIn("user", result)
        self.assertIn("name", result["user"])
        self.assertEqual(len(result["user"]["name"]), 30)
        self.assertIn("address", result["user"])
        self.assertEqual(len(result["user"]["address"]["city"]), 50)
        self.assertEqual(len(result["user"]["address"]["zip"]), 10)

    def test_additional_properties(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "additionalProperties": {"type": "string", "maxLength": 20}
        }
        result = generate_from_schema(schema)
        self.assertIn("id", result)
        # 3 extra fields
        extra_keys = [k for k in result if k.startswith("extra_")]
        self.assertEqual(len(extra_keys), 3)
        for k in extra_keys:
            self.assertEqual(len(result[k]), 20)


class TestArrays(unittest.TestCase):
    def test_array_max_items(self):
        schema = {
            "type": "array",
            "maxItems": 7,
            "items": {"type": "integer", "maximum": 100}
        }
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 7)
        for item in result:
            self.assertEqual(item, 100)

    def test_array_default_items(self):
        schema = {"type": "array", "items": {"type": "boolean"}}
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 5)
        for item in result:
            self.assertTrue(item)

    def test_array_min_items(self):
        schema = {"type": "array", "minItems": 3, "items": {"type": "string", "maxLength": 10}}
        result = generate_from_schema(schema)
        self.assertGreaterEqual(len(result), 3)

    def test_array_of_objects(self):
        schema = {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "label": {"type": "string", "maxLength": 15}
                }
            }
        }
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 3)
        for item in result:
            self.assertIn("id", item)
            self.assertIn("label", item)
            self.assertEqual(len(item["label"]), 15)


class TestPatterns(unittest.TestCase):
    def test_digit_pattern(self):
        schema = {"type": "string", "pattern": "^\\d+$", "maxLength": 10}
        result = generate_from_schema(schema)
        self.assertLessEqual(len(result), 10)
        # Should be digits
        self.assertTrue(all(c.isdigit() or len(result) == 0 for c in result))

    def test_word_pattern(self):
        schema = {"type": "string", "pattern": "^\\w+$", "maxLength": 20}
        result = generate_from_schema(schema)
        self.assertLessEqual(len(result), 20)
        self.assertGreater(len(result), 0)

    def test_char_class_pattern(self):
        schema = {"type": "string", "pattern": "^[a-z]+$", "maxLength": 15}
        result = generate_from_schema(schema)
        self.assertLessEqual(len(result), 15)
        self.assertGreater(len(result), 0)


class TestRefs(unittest.TestCase):
    def test_ref_defs(self):
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "maxLength": 100},
                        "city": {"type": "string", "maxLength": 50},
                    }
                }
            },
            "type": "object",
            "properties": {
                "home": {"$ref": "#/$defs/Address"},
                "work": {"$ref": "#/$defs/Address"},
            }
        }
        result = generate_from_schema(schema)
        self.assertIn("home", result)
        self.assertIn("work", result)
        self.assertEqual(len(result["home"]["street"]), 100)
        self.assertEqual(len(result["work"]["city"]), 50)

    def test_ref_definitions(self):
        schema = {
            "definitions": {
                "Tag": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "maxLength": 20},
                        "value": {"type": "integer"}
                    }
                }
            },
            "type": "array",
            "maxItems": 2,
            "items": {"$ref": "#/definitions/Tag"}
        }
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]["name"]), 20)


class TestCombiners(unittest.TestCase):
    def test_all_of(self):
        schema = {
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "maxLength": 30}
                    }
                },
                {
                    "type": "object",
                    "properties": {
                        "age": {"type": "integer", "maximum": 99}
                    }
                }
            ]
        }
        result = generate_from_schema(schema)
        self.assertIn("name", result)
        self.assertIn("age", result)
        self.assertEqual(len(result["name"]), 30)
        self.assertEqual(result["age"], 99)

    def test_any_of(self):
        schema = {
            "anyOf": [
                {"type": "object", "properties": {"x": {"type": "integer"}}},
                {"type": "object", "properties": {"y": {"type": "string", "maxLength": 10}}},
            ]
        }
        result = generate_from_schema(schema)
        # Should have fields from at least one (merged: both)
        self.assertTrue("x" in result or "y" in result)

    def test_one_of(self):
        schema = {
            "oneOf": [
                {"type": "object", "properties": {"code": {"type": "string", "maxLength": 5}}}
            ]
        }
        result = generate_from_schema(schema)
        self.assertIn("code", result)
        self.assertEqual(len(result["code"]), 5)

    def test_all_of_with_ref(self):
        schema = {
            "$defs": {
                "Base": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"}
                    }
                }
            },
            "allOf": [
                {"$ref": "#/$defs/Base"},
                {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "maxLength": 25}
                    }
                }
            ]
        }
        result = generate_from_schema(schema)
        self.assertIn("id", result)
        self.assertIn("label", result)
        self.assertEqual(len(result["label"]), 25)


class TestMultipleTypes(unittest.TestCase):
    def test_multiple_types_picks_non_null(self):
        schema = {"type": ["string", "null"], "maxLength": 10}
        result = generate_from_schema(schema)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 10)

    def test_only_null_type(self):
        schema = {"type": ["null"]}
        result = generate_from_schema(schema)
        self.assertIsNone(result)


class TestEdgeCases(unittest.TestCase):
    def test_empty_schema(self):
        schema = {}
        result = generate_from_schema(schema)
        # Should not crash, returns empty object or similar
        self.assertIsInstance(result, dict)

    def test_no_type_with_properties(self):
        schema = {"properties": {"foo": {"type": "string", "maxLength": 5}}}
        result = generate_from_schema(schema)
        self.assertIn("foo", result)
        self.assertEqual(len(result["foo"]), 5)

    def test_exclusive_maximum_integer(self):
        schema = {"type": "integer", "exclusiveMaximum": 10}
        result = generate_from_schema(schema)
        self.assertLess(result, 10)

    def test_exclusive_maximum_number(self):
        schema = {"type": "number", "exclusiveMaximum": 5.0}
        result = generate_from_schema(schema)
        self.assertLess(result, 5.0)

    def test_prefix_items(self):
        schema = {
            "type": "array",
            "maxItems": 3,
            "prefixItems": [
                {"type": "string", "maxLength": 5},
                {"type": "integer", "maximum": 10},
            ],
            "items": {"type": "boolean"}
        }
        result = generate_from_schema(schema)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], str)
        self.assertEqual(len(result[0]), 5)
        self.assertIsInstance(result[1], int)
        self.assertEqual(result[1], 10)
        self.assertIsInstance(result[2], bool)


class TestComplexRealWorld(unittest.TestCase):
    def test_user_profile_schema(self):
        schema = {
            "type": "object",
            "required": ["id", "username", "email"],
            "properties": {
                "id": {"type": "integer", "maximum": 2147483647},
                "username": {"type": "string", "minLength": 3, "maxLength": 32, "pattern": "^[a-zA-Z0-9_]+$"},
                "email": {"type": "string", "format": "email", "maxLength": 255},
                "bio": {"type": "string", "maxLength": 500},
                "age": {"type": "integer", "minimum": 0, "maximum": 150},
                "score": {"type": "number", "minimum": 0.0, "maximum": 100.0},
                "verified": {"type": "boolean"},
                "tags": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {"type": "string", "maxLength": 20}
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "created_at": {"type": "string", "format": "date-time"},
                        "source": {"type": "string", "enum": ["web", "mobile", "api"]},
                    }
                }
            }
        }
        result = generate_from_schema(schema)

        # All fields present
        for field in ["id", "username", "email", "bio", "age", "score", "verified", "tags", "metadata"]:
            self.assertIn(field, result)

        # Lengths respected
        self.assertLessEqual(len(result["username"]), 32)
        self.assertLessEqual(len(result["email"]), 255)
        self.assertEqual(len(result["bio"]), 500)

        # Numbers
        self.assertEqual(result["id"], 2147483647)
        self.assertEqual(result["age"], 150)
        self.assertEqual(result["score"], 100.0)

        # Array
        self.assertEqual(len(result["tags"]), 10)
        for tag in result["tags"]:
            self.assertEqual(len(tag), 20)

        # Nested
        self.assertIn("T", result["metadata"]["created_at"])
        self.assertEqual(result["metadata"]["source"], "mobile")  # longest enum


class TestPatternFallbackBugs(unittest.TestCase):
    """Regression tests for _fill_pattern_fallback bugs."""

    def test_uuid_pattern_has_dashes(self):
        """Bug 1: UUID pattern must include literal dash separators."""
        schema = {
            "type": "string",
            "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        }
        result = generate_from_schema(schema)
        # Must contain dashes in the right positions
        self.assertEqual(result[8], '-')
        self.assertEqual(result[13], '-')
        self.assertEqual(result[18], '-')
        self.assertEqual(result[23], '-')
        # Total length: 8+1+4+1+4+1+4+1+12 = 36
        self.assertEqual(len(result), 36)
        # All non-dash chars should be valid hex
        hex_chars = result.replace('-', '')
        self.assertTrue(all(c in '0123456789abcdefABCDEF' for c in hex_chars))

    def test_char_class_diversity(self):
        """Bug 2: Character classes should use diverse characters, not just the first."""
        schema = {
            "type": "string",
            "pattern": "^[0-9a-zA-Z_-]{1,50}$",
        }
        result = generate_from_schema(schema)
        # Should have more than one unique character
        unique_chars = set(result)
        self.assertGreater(len(unique_chars), 1,
                           f"Expected diverse characters but got: {result!r}")

    def test_cyrillic_char_class_diversity(self):
        """Bug 2 variant: Cyrillic + Latin character classes should be diverse."""
        from json_schema_generator import _fill_pattern_fallback
        result = _fill_pattern_fallback("^[0-9a-zA-Zа-яА-Я\\s_-]{1,50}$", 50)
        unique_chars = set(result)
        self.assertGreater(len(unique_chars), 1,
                           f"Expected diverse characters but got: {result!r}")
        self.assertEqual(len(result), 50)

    def test_quantifier_exact(self):
        """Exact quantifiers like {8} produce exactly 8 characters."""
        from json_schema_generator import _fill_pattern_fallback
        result = _fill_pattern_fallback("^[a-z]{5}$", 100)
        self.assertEqual(len(result), 5)

    def test_literal_chars_preserved(self):
        """Literal characters in patterns are preserved."""
        from json_schema_generator import _fill_pattern_fallback
        result = _fill_pattern_fallback("^hello$", 100)
        self.assertEqual(result, "hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
