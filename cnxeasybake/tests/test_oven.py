# -*- coding: utf-8 -*-
"""Tests for the Oven class."""
import unittest
import os
import tempfile
from contextlib import contextmanager
from StringIO import StringIO


@contextmanager
def tempinput(data):
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp.write(data)
    temp.close()
    yield temp.name
    os.unlink(temp.name)

CSS = 'div { copy-to: end-of-chapter;}'


class OvenCssTest(unittest.TestCase):
    """Oven Css test cases.

    Test ways to load and replace CSS in an oven instance
    """

    maxDiff = None

    @property
    def target_cls(self):
        """Import the target class."""
        from ..oven import Oven
        return Oven

    def test_no_css(self):
        """Test empty oven."""
        oven = self.target_cls()

    def test_string_css(self):
        """Test oven with initial CSS as string."""
        oven = self.target_cls(CSS)

    def test_fileob_css(self):
        """Test oven with initial CSS as open file handle."""
        css_f = StringIO(CSS)
        oven = self.target_cls(css_f)

    def test_filename_css(self):
        """Test ocen with initial CSS as a filename to open."""
        with tempinput(CSS) as tempfilename:
            oven = self.target_cls(tempfilename)