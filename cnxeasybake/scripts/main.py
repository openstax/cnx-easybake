#!/usr/bin/env python
"""Use baker from command line."""
from __future__ import print_function

import argparse
import logging
import sys
from lxml import etree

from cnxeasybake import Oven

logger = logging.getLogger('cnx-easybake')


def easybake(css_in, html_in=sys.stdin, html_out=sys.stdout):
    """Process the given HTML file stream with the css stream."""
    html_parser = etree.HTMLParser()
    html_doc = etree.HTML(html_in.read(), html_parser)
    oven = Oven(css_in)
    oven.bake(html_doc)

    # serialize out HTML
    print (etree.tostring(html_doc, method="html"), file=html_out)


def main(argv=None):
    """Commandline script wrapping Baker."""
    parser = argparse.ArgumentParser(description="Process raw HTML to cooked"
                                                 " (embedded numbering and"
                                                 " collation)")
    parser.add_argument("css_rules", help="CSS3 ruleset stylesheet recipe")
    parser.add_argument("html_in", nargs="?",
                        type=argparse.FileType('r'),
                        help="raw HTML file to cook (default stdin)",
                        default=sys.stdin)
    parser.add_argument("html_out", nargs="?",
                        type=argparse.FileType('w'),
                        help="cooked HTML file output (default stdout)",
                        default=sys.stdout)
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Send debugging info to stderr')
    args = parser.parse_args(argv)

    formatter = logging.Formatter('%(name)s %(levelname)s %(message)s')
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    easybake(args.css_rules, args.html_in, args.html_out)

if __name__ == "__main__":
    main(sys.argv[1:])
