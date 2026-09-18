"""Strict JSON schemas for structured output

Providers that enforce a response schema (Anthropic structured outputs,
OpenAI strict json_schema) require a conservative dialect: every object
closed with ``additionalProperties: false``, every property listed in
``required``, and no references. Numeric and string range keywords are not
supported by every provider, so they are stripped here and enforced instead
by Pydantic validation after parsing.
"""

import copy
from typing import Any, Dict, Type

from pydantic import BaseModel

# Keywords removed from provider-facing schemas. Pydantic still enforces them
# when the parsed output is validated, so no constraint is lost.
_UNSUPPORTED_KEYWORDS = {
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
}


def strict_json_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Provider-safe JSON schema for a Pydantic model"""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return _normalise(schema, definitions)


def _normalise(node: Any, definitions: Dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_normalise(item, definitions) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        return _normalise(copy.deepcopy(definitions[name]), definitions)

    result: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            # Property names are data, not keywords - a field called "title"
            # or "format" must survive the keyword filter.
            result[key] = {name: _normalise(sub, definitions) for name, sub in value.items()}
        elif key not in _UNSUPPORTED_KEYWORDS:
            result[key] = _normalise(value, definitions)

    if result.get("type") == "object" and "properties" in result:
        result["required"] = list(result["properties"].keys())
        result["additionalProperties"] = False

    return result
