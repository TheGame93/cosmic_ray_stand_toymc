"""Tests for the button-widget factory used by the event display's nav row."""

from __future__ import annotations

import unittest

import numpy as np

from toymc_cosmic.gui.buttons import build_button_texture_pixels, build_navigation_button_specs
from toymc_cosmic.gui.layout import BUTTON_LEFT_PADDING_PX, BUTTON_ROW_Y_PX, BUTTON_SIZE_PX


class GuiButtonsTests(unittest.TestCase):
    """Check button layout and icon-texture generation."""

    def test_navigation_button_specs_form_one_horizontal_row_left_aligned_under_axes(self) -> None:
        """Buttons should sit directly under the axes, left-aligned, in Home/Previous/Next order."""
        button_specs = build_navigation_button_specs()

        self.assertEqual([spec.name for spec in button_specs], ["Home", "Previous", "Next"])
        self.assertEqual([spec.icon_kind for spec in button_specs], ["home", "previous", "next"])
        self.assertTrue(all(spec.position[1] == BUTTON_ROW_Y_PX for spec in button_specs))
        self.assertEqual(button_specs[0].position[0], float(BUTTON_LEFT_PADDING_PX))
        self.assertTrue(button_specs[0].position[0] < button_specs[1].position[0] < button_specs[2].position[0])

    def test_button_texture_icons_have_expected_shape_and_mirroring(self) -> None:
        """Home should be a square, while Previous/Next should be mirrored arrows."""
        home_pixels = build_button_texture_pixels("home", is_pressed=False, size=BUTTON_SIZE_PX)
        previous_pixels = build_button_texture_pixels("previous", is_pressed=False, size=BUTTON_SIZE_PX)
        next_pixels = build_button_texture_pixels("next", is_pressed=False, size=BUTTON_SIZE_PX)

        self.assertEqual(home_pixels.dtype, np.uint8)
        self.assertEqual(home_pixels.shape, (BUTTON_SIZE_PX, BUTTON_SIZE_PX, 3))
        self.assertTrue(np.array_equal(previous_pixels[:, ::-1, :], next_pixels))
        self.assertFalse(np.array_equal(home_pixels, previous_pixels))

        center = BUTTON_SIZE_PX // 2
        self.assertTrue(np.array_equal(home_pixels[center, center], home_pixels[center - 1, center - 1]))
        self.assertFalse(np.array_equal(home_pixels[center, center], home_pixels[1, 1]))
