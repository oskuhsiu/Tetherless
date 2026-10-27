"""Avoid collision with the inherited UIKit Button class. Native CI type-checks it."""
from pathlib import Path
import re
import unittest

class UINamespaceTests(unittest.TestCase):
    def test_native_form_uses_swiftui_button(self):
        source = (Path(__file__).parents[1] / 'Native/NativeRenewalSettings.swift').read_text()
        self.assertIsNone(re.search(r'(?<![\w.])Button\s*\(', source))
        self.assertGreaterEqual(source.count('SwiftUI.Button('), 3)
        self.assertNotRegex(source, r'(?<![\w.])Button\s*\(')
