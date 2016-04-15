# -*- coding: utf-8 -*-
"""Test all rulesets."""
import glob
import os
import subprocess
import unittest
import logging
from testfixtures import log_capture

from lxml import etree

from ..oven import Oven

here = os.path.abspath(os.path.dirname(__file__))
TEST_RULESET_DIR = os.path.join(here, 'rulesets')
TEST_HTML_DIR = os.path.join(here, 'html')

logger = logging.getLogger('cnx-easybake')
logger.setLevel(logging.DEBUG)


def tidy(input_):
    """Pretty Print XHTML."""
    proc = subprocess.Popen(['{}/utils/xmlpp.pl'.format(here), '-sSten'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    output, _ = proc.communicate(input_)
    return output


def lessc(input_):
    """Convert less to css."""
    proc = subprocess.Popen(['lessc', '-'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    output, _ = proc.communicate(input_)
    return output


class RulesetTestCase(unittest.TestCase):
    """Ruleset test cases.

    Use easybake to transform <name>_raw.html with <name>.less and compare
    with <name>_cooked.html files
    """

    maxDiff = None

    @classmethod
    def generate_tests(cls):
        """Build tests from css and html files."""
        for less_filename in glob.glob(os.path.join(TEST_RULESET_DIR,
                                       '*.less')):
            filename_no_ext = less_filename.rsplit('.less', 1)[0]
            header = []
            logs = []
            desc = None
            with open('{}.less'.format(filename_no_ext), 'rb') as f_less:
                for line in f_less:
                    if line.startswith('// '):
                        header.append(line[3:])
                f_less.seek(0)
                css_fname = '{}.css'.format(filename_no_ext)
                fnum = f_less.fileno()

                if not os.path.isfile(css_fname) or \
                   os.fstat(fnum).st_mtime > os.stat(css_fname).st_mtime:
                    with open(css_fname, 'wb') as f_css:
                        f_css.write(lessc(f_less.read()))

            if len(header) > 0:
                desc = header[0]
            for hline in header:
                if hline.startswith('LOG: '):
                    logs.append(tuple(hline[:-1].split(None, 3)[1:]))
            if len(logs) > 0:
                logs = tuple(logs)

            test_name = os.path.basename(filename_no_ext)
            with open(os.path.join(TEST_HTML_DIR,
                                   '{}_cooked.html'.format(test_name)),
                      'rb') as f:
                cooked_html = tidy(f.read())

            with open(os.path.join(TEST_HTML_DIR,
                                   '{}_raw.html'.format(test_name)),
                      'rb') as f:
                html = f.read()

            setattr(cls, 'test_{}'.format(test_name),
                    cls.create_test('{}.css'.format(filename_no_ext),
                                    html, cooked_html, desc, logs))

    @classmethod
    def create_test(cls, css, html, cooked_html, desc, logs):
        """Create a specific ruleset test."""
        @log_capture()
        def run_test(self, logcap):
            element = etree.HTML(html)
            oven = Oven(css)
            oven.bake(element)
            output = tidy(etree.tostring(element, method='html'))
            # https://bugs.python.org/issue10164
            self.assertEqual(output.split(b'\n'), cooked_html.split(b'\n'))
            if len(logs) == 0:
                logcap.check()
            else:
                logcap.check(*logs)

        if desc:
            run_test.__doc__ = desc
        return run_test


RulesetTestCase.generate_tests()
