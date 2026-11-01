"""Behavioral checks for the public BC7 encoder and decoder."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from ddiconstudio import bc7  # noqa: E402


class Bc7CodecTests(unittest.TestCase):
    def test_solid_block_round_trip(self):
        source = np.empty((4, 4, 4), dtype=np.uint8)
        source[:] = (19, 83, 147, 255)

        encoded = bc7.codificar(source)

        self.assertEqual(len(encoded), 256)
        self.assertEqual(encoded[0] & 0x7F, 0x40)
        np.testing.assert_allclose(bc7.decodificar(encoded, 4, 4), source, atol=1, rtol=0)

    def test_block_layout_and_row_pitch(self):
        source = np.empty((8, 8, 4), dtype=np.uint8)
        source[:4, :4] = (40, 80, 120, 255)
        source[:4, 4:] = (0, 0, 0, 0)
        source[4:, :4] = (210, 70, 30, 255)
        source[4:, 4:] = (200, 50, 10, 0)

        encoded = bc7.codificar(source)

        self.assertEqual(len(encoded), 512)
        np.testing.assert_allclose(bc7.decodificar(encoded, 8, 8), source, atol=1, rtol=0)

    def test_transparent_pixels_keep_neighbor_color_without_alpha(self):
        source = np.zeros((4, 4, 4), dtype=np.uint8)
        source[0, 0] = (200, 100, 50, 255)

        decoded = np.asarray(bc7.decodificar(bc7.codificar(source), 4, 4))

        np.testing.assert_array_equal(decoded[..., :3], np.broadcast_to((200, 100, 50), (4, 4, 3)))
        self.assertLessEqual(abs(int(decoded[0, 0, 3]) - 255), 1)
        self.assertTrue((decoded[1:, :, 3] == 0).all())
        self.assertTrue((decoded[0, 1:, 3] == 0).all())


if __name__ == "__main__":
    unittest.main()