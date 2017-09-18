# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""CLI tests."""
import logging
import os
import sys
import tempfile
import unittest

from contextlib import contextmanager
from io import StringIO


# noqa from http://stackoverflow.com/questions/4219717/how-to-assert-output-with-nosetest-unittest-in-python
@contextmanager
def captured_output():
    if sys.version_info[0] == 3:
        new_out, new_err = StringIO(), StringIO()
    else:
        from io import BytesIO
        new_out, new_err = BytesIO(), BytesIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        for handler in logging.root.handlers:
            if hasattr(handler, 'stream'):
                if handler.stream == sys.stderr:
                    handler.stream = new_err
                elif handler.stream == sys.stdout:
                    handler.stream = new_out
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        for handler in logging.root.handlers:
            if hasattr(handler, 'stream'):
                if handler.stream == new_err:
                    handler.stream = old_err
                elif handler.stream == new_out:
                    handler.stream = old_out

here = os.path.abspath(os.path.dirname(__file__))


class CliTestCase(unittest.TestCase):
    """Test the cli."""

    @property
    def target(self):
        """the program under test."""
        from cnxeasybake.scripts.main import main
        return main

    def test_success(self):
        """Call cli with basic successful run."""
        os.chdir(here)
        with captured_output() as (out, err):
            args = ['rulesets/empty.css', 'html/empty_raw.html', '/dev/null']
            self.target(args)
            stdout = str(out.getvalue())
            stderr = str(err.getvalue())

        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')

    def test_failure(self):
        """Call cli with basic unsuccessful run."""
        os.chdir(here)
        threw_an_error = False
        with captured_output() as (out, err):
            args = ['invalid.css', 'html/empty_raw.html', '/dev/null']
            try:
                self.target(args)
            except:
                threw_an_error = True
            stdout = str(out.getvalue())
            stderr = str(err.getvalue())

        self.assertEqual(threw_an_error, True, 'Should have thrown an error')
        self.assertEqual(stderr, 'cnx-easybake ERROR Parse Error invalid: EOF reached before {} block for a qualified rule.\n')
        self.assertEqual(stdout, '')

    def test_noargs(self):
        """Check basic usage message."""
        os.chdir(here)
        with captured_output() as (out, err):
            args = []
            try:
                self.target(args)
            except:
                pass
            stdout = str(out.getvalue())
            stderr = str(err.getvalue())

        self.assertEqual(stdout, '')
        self.assertIn("error: too few arguments", stderr)

    def test_help(self):
        """Check help usage message."""
        os.chdir(here)
        with captured_output() as (out, err):
            args = ['-h']
            try:
                self.target(args)
            except:
                pass
            stdout = str(out.getvalue())
            stderr = str(err.getvalue())

        usage_message = """[-h] [-v] [-s <pass>] [-d] [-c coverage.lcov]
                [--use-repeatable-ids]
                css_rules [html_in] [html_out]

Process raw HTML to baked (embedded numbering and collation)

positional arguments:
  css_rules             CSS3 ruleset stylesheet recipe
  html_in               raw HTML file to bake (default stdin)
  html_out              baked HTML file output (default stdout)

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         Report the library version
  -s <pass>, --stop-at <pass>
                        Stop baking just before given pass name
  -d, --debug           Send debugging info to stderr
  -c coverage.lcov, --coverage-file coverage.lcov
                        output coverage file (lcov format). If filename starts
                        with '+', append coverage info.
  --use-repeatable-ids  use repeatable id attributes instead of uuids which is
                        useful for diffing
"""

        self.assertEqual(stderr, '')
        self.assertIn(usage_message.replace(' ', ''), stdout.replace(' ', ''))

    def test_coverage(self):
        """Call cli coverage output."""
        os.chdir(here)
        fs_pointer, lcov_filepath = tempfile.mkstemp('.lcov')
        self.addCleanup(os.remove, lcov_filepath)

        args = ['--coverage-file', lcov_filepath, 'rulesets/clear.css',
                'html/clear_raw.html', '/dev/null']
        with captured_output() as (out, err):
            try:
                self.target(args)
            except:
                pass
            stdout = str(out.getvalue())
            stderr = str(err.getvalue())

        coverage_expected = """SF:rulesets/clear.css
DA:2,0
DA:6,0
DA:2,1
DA:3,1
DA:6,1
DA:7,1
end_of_record
"""
        coverage_actual = os.read(fs_pointer, 8192)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')
        self.assertEqual(coverage_actual, coverage_expected)
