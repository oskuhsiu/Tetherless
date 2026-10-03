from pathlib import Path
import unittest

class ScrollGeometryTests(unittest.TestCase):
    def test_known_target_guides_direction_without_coordinate_taps(self):
        text=(Path(__file__).parents[1]/'UITests/TetherlessUITests.swift').read_text()
        for value in ['element.frame.maxY > bottom','element.frame.minY < top',
                      'app.tabBars.firstMatch.frame.minY','form.swipeDown(velocity: .slow)',
                      'form.swipeUp(velocity: .slow)','for _ in 0..<6']:
            self.assertIn(value,text)
        self.assertNotIn('coordinate(withNormalizedOffset:',text)
