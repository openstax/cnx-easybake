# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""CLI tests."""
import os
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

here = os.path.abspath(os.path.dirname(__file__))


class CliTestCase(unittest.TestCase):
    """Test the cli."""

    @property
    def target(self):
        """the program under test."""
        from cnxeasybake.scripts.main import main
        return main

    @mock.patch('sys.stderr')
    def test_help(self, mocked_stderr):
        """Call cli with basic successful run."""
        os.chdir(here)
        args = ['rulesets/empty.css', 'html/empty_raw.html', '/dev/null']
        return_code = self.target(args)
        self.assertEqual(return_code, None)

        # Ensure a meaningfully message was sent to stderr.
        # expected_message_line = 'too few arguments'
        # mocked_stderr.write.assert_any_call(expected_message_line)
