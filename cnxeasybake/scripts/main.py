#!/usr/bin/env python
"""Use baker from command line."""
from __future__ import print_function

import argparse
import logging
import sys
from lxml import etree

from cnxeasybake import Oven, __version__

logger = logging.getLogger('cnx-easybake')


def easybake(css_in, html_in=sys.stdin, html_out=sys.stdout, last_step=None,
             coverage_file=None, use_repeatable_ids=False):
    """Process the given HTML file stream with the css stream."""
    html_doc = etree.parse(html_in)
    oven = Oven(css_in, use_repeatable_ids)
    oven.bake(html_doc, last_step)

    # serialize out HTML
    print (etree.tostring(html_doc, method="xml"), file=html_out)

    # generate CSS coverage_file file
    if coverage_file:
        print('SF:{}'.format(css_in.name), file=coverage_file)
        print(oven.get_coverage_report(), file=coverage_file)
        print('end_of_record', file=coverage_file)


class FileTypeExt(argparse.FileType):
    """FileType that extends if filename starts with + and mode = 'w'"""

    def __call__(self, string):
        if string.startswith('+'):
            string = string[1:]
            if self._mode == 'w':
                self._mode = 'a'
        return super(FileTypeExt, self).__call__(string)


def main(argv=None):
    """Commandline script wrapping Baker."""
    parser = argparse.ArgumentParser(description="Process raw HTML to baked"
                                                 " (embedded numbering and"
                                                 " collation)")
    parser.add_argument('-v', '--version', action="version",
                        version=__version__, help='Report the library version')
    parser.add_argument("css_rules",
                        type=argparse.FileType('r'),
                        help="CSS3 ruleset stylesheet recipe")
    parser.add_argument("html_in", nargs="?",
                        type=argparse.FileType('r'),
                        help="raw HTML file to bake (default stdin)",
                        default=sys.stdin)
    parser.add_argument("html_out", nargs="?",
                        type=argparse.FileType('w'),
                        help="baked HTML file output (default stdout)",
                        default=sys.stdout)
    parser.add_argument('-s', '--stop-at', action='store', metavar='<pass>',
                        help='Stop baking just before given pass name')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Send debugging info to stderr')
    parser.add_argument('-c', '--coverage-file', metavar='coverage.lcov',
                        type=FileTypeExt('w'),
                        help="output coverage file (lcov format). If "
                        "filename starts with '+', append coverage info.")
    parser.add_argument('--use-repeatable-ids', action='store_true',
                        help="use repeatable id attributes instead of uuids "
                        "which is useful for diffing")
    args = parser.parse_args(argv)

    formatter = logging.Formatter('%(name)s %(levelname)s %(message)s')
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    easybake(args.css_rules, args.html_in, args.html_out, args.stop_at,
             args.coverage_file, args.use_repeatable_ids)


if __name__ == "__main__":
    main(sys.argv[1:])
