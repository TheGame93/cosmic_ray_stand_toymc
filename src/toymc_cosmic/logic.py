"""Safe evaluation of boolean detector logic expressions."""

from __future__ import annotations

import ast

import numpy as np


def evaluate(expression: str, context: dict[str, np.ndarray]) -> np.ndarray:
    """Evaluate a boolean detector expression against array-valued inputs.

    Args:
        expression: Expression such as `"T1 and T2 and not D1"`.
        context: Mapping from detector names to boolean numpy arrays.

    Returns:
        Boolean numpy array with one value per simulated event.
    """

    parsed_expression = _parse_expression(expression)
    return _evaluate_node(parsed_expression.body, context)


def extract_names(expression: str) -> set[str]:
    """Return the detector names referenced by a validated expression."""
    parsed_expression = _parse_expression(expression)
    names: set[str] = set()

    for node in ast.walk(parsed_expression):
        if isinstance(node, ast.Name):
            names.add(node.id)

    return names


def _parse_expression(expression: str) -> ast.Expression:
    """Parse and validate a boolean detector expression."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Logic expression must be a non-empty string.")

    try:
        parsed_expression = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid logic expression: {expression!r}") from exc

    _validate_node(parsed_expression.body)
    return parsed_expression


def _validate_node(node: ast.AST) -> None:
    """Recursively validate that only simple boolean syntax is used."""
    if isinstance(node, ast.Name):
        return

    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise ValueError("Only 'and' and 'or' boolean operators are allowed.")
        for value in node.values:
            _validate_node(value)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.Not):
            raise ValueError("Only the 'not' unary operator is allowed.")
        _validate_node(node.operand)
        return

    raise ValueError(
        "Only detector names with 'and', 'or', and 'not' are allowed in logic expressions."
    )


def _evaluate_node(node: ast.AST, context: dict[str, np.ndarray]) -> np.ndarray:
    """Recursively evaluate a validated AST node."""
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ValueError(f"Unknown detector name in expression: {node.id}")
        return np.asarray(context[node.id], dtype=bool)

    if isinstance(node, ast.BoolOp):
        values = [_evaluate_node(value, context) for value in node.values]
        if isinstance(node.op, ast.And):
            return np.logical_and.reduce(values)
        return np.logical_or.reduce(values)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return np.logical_not(_evaluate_node(node.operand, context))

    raise ValueError("Unexpected node reached during logic evaluation.")
