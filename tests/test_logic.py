"""Tests for logic expression parsing and evaluation."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.logic import evaluate, extract_names


class LogicTests(unittest.TestCase):
    """Check allowed and rejected boolean syntax."""

    def test_valid_expression_evaluates(self) -> None:
        """Boolean expressions should evaluate element-wise."""
        context = {
            "T1": np.array([True, True, False]),
            "T2": np.array([True, False, False]),
            "D1": np.array([False, True, False]),
        }

        result = evaluate("T1 and T2 and not D1", context)
        self.assertTrue(np.array_equal(result, np.array([True, False, False])))
        self.assertEqual(extract_names("T1 and T2 and not D1"), {"T1", "T2", "D1"})

    def test_invalid_expression_raises(self) -> None:
        """Disallowed Python syntax must be rejected."""
        with self.assertRaises(ValueError):
            evaluate("T1 == T2", {"T1": np.array([True]), "T2": np.array([True])})

        with self.assertRaises(ValueError):
            evaluate("T1()", {"T1": np.array([True])})
