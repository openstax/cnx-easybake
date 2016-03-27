# -*- coding: utf-8 -*-
import glob
import os
import subprocess
import unittest

from lxml import etree

from ..oven import Oven

here = os.path.abspath(os.path.dirname(__file__))
TEST_RULESET_DIR = os.path.join(here, 'rulesets')
TEST_HTML_DIR = os.path.join(here, 'html')


def tidy(input_):
    """Pretty Print XHTML"""
    proc = subprocess.Popen(['tidy', '-xml', '-qi'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    output, _ = proc.communicate(input_)
    return output


def lessc(input_):
    """Convert less to css"""
    proc = subprocess.Popen(['lessc', '-'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    output, _ = proc.communicate(input_)
    return output


class RulesetTestCase(unittest.TestCase):
    """Ruleset test cases

    Use easybake to transform <name>_raw.html with <name>.less and compare
    with <name>_cooked.html files
    """

    maxDiff = None

    @classmethod
    def generate_tests(cls):
        for less_filename in glob.glob(os.path.join(TEST_RULESET_DIR,
                                       '*.less')):
            filename_no_ext = less_filename.rsplit('.less', 1)[0]
            with open('{}.less'.format(filename_no_ext), 'rb') as f_less:
                with open('{}.css'.format(filename_no_ext), 'wb') as f_css:
                    f_css.write(lessc(f_less.read()))

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
                                    html, cooked_html))

    @classmethod
    def create_test(cls, css, html, cooked_html):
        def run_test(self):
            element = etree.HTML(html)
            oven = Oven(css)
            oven.bake(element)
            output = tidy(etree.tostring(element))

            # https://bugs.python.org/issue10164
            self.assertEqual(output.split(b'\n'), cooked_html.split(b'\n'))
        return run_test


RulesetTestCase.generate_tests()
