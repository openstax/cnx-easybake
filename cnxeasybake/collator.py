#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
from __future__ import print_function
import sys
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list
import cssselect2
from cssselect2 import ElementWrapper
import argparse
import functools
import copy

collation_decls = [(u'move-to', ''),
                   (u'copy-to', ''),
                   (u'content', u'pending')]

labeling_decls = [(u'string-set', ''),
                  (u'class', '')]

numbering_decls = [(u'counter-reset', ''),
                   (u'counter-increment', ''),
                   (u'content', u'counter'),
                   (u'content', u'target-counter')]


def main(css_in, html_in=sys.stdin, html_out=sys.stdout):
    """Process the given HTML file stream with the css stream."""
    html_parser = etree.HTMLParser()

    html_doc = etree.HTML(html_in.read(), html_parser)

    # Recurse down tree, applying CSS collation
    # At each level, check what rules match. Apply 'toplevel' ones,
    # then recurse, and apply 'after' ones.

    collate = Collator(css_in)

    wrapped_html_tree = ElementWrapper.from_html_root(html_doc)
    collate.do_collation(wrapped_html_tree)

    # loop over pending dictionaries, doing moves and copies to etree

    for key, actions in collate.state['pending'].iteritems():
        target = None
        for action, value in actions:
            if action == 'target':
                target = value
            elif action == 'move':
                target.append(value)
            elif action == 'copy':
                target.append(copy.deepcopy(value))

    # Do numbering

    # Do label/link updates

    # serialize out HTML
    print (etree.tostring(html_doc), file=html_out)


class Collator():
    """Collate HTML with CSS3.

    An object that parses and stores rules defined in CSS3 and can apply
    them to an HTML file.
    """

    def __init__(self, css_in=None):
        """Initialize collator, with optional inital CSS."""
        matcher = cssselect2.Matcher()
        self.matcher = matcher
        if css_in:
            self.update_css(css_in)
        self.state = {}
        self.state['pending'] = {}
        self.state['pending_elems'] = []
        self.state['counters'] = {}
        self.state['strings'] = {}

    def update_css(self, css_in=None, clear=False):
        """Add additional CSS rules, optionally replacing all."""
        # FIXME make polymorphic on css - bytes, fileobj, path to open ...
        if css_in is None:
            return

        if clear:
            self.matcher = cssselect2.Matcher()

        rules, _ = tinycss2.parse_stylesheet_bytes(css_in.read(),
                                                   skip_whitespace=True)
        for rule in rules:
            # Ignore all at-rules
            if rule.type == 'qualified-rule':
                try:
                    selectors = cssselect2.compile_selector_list(rule.prelude)
                except cssselect2.SelectorError as error:
                    debug('Invalid selector: %s %s'
                          % (serialize(rule.prelude), error))
                else:
                    if is_collation_rule(rule):
                        for selector in selectors:
                            self.matcher.add_selector(selector, rule)

    def do_collation(self, element, depth=0):
        """Do the thing - collate an HTML doc starting from the element."""
        # Rules match during a recusive descent HTML tree walk. Each
        # declaration has a method that then runs, given the current element,
        # the decaration value. State is maintained on the collator instance.
        # Since matching occurs when entering a node, it's children have not
        # yet been visited, so each declaration method can optionally return a
        # deferred method to run when the current node's children have been
        # processed.
        deferred = []
        for rule in self.matcher.match(element):
            declarations = parse_declaration_list(rule.content,
                                                  skip_whitespace=True)
            for decl in declarations:
                method = getattr(self, 'do_{}'.format(
                                 decl.name).replace('-', '_'))
                deferred.append(method(element, decl.value))

        for el in element.iter_children():
            _state = self.do_collation(el, depth=depth+1)  # noqa

        if any(deferred):
            for d in deferred:
                if d:
                    d(element)

        return self.state

    def do_copy_to(self, element, value):
        """Implement copy-to declaration - pre-match."""
        debug(element.local_name, 'copy-to', serialize(value))
        target = serialize(value).strip()
        self.state['pending'].setdefault(target, []).append(
                                         ('copy', element.etree_element))

    def do_move_to(self, element, value):
        """Implement move-to declaration - pre-match."""
        debug(element.local_name, 'move-to', serialize(value))
        target = serialize(value).strip()
        self.state['pending'].setdefault(target, []).append(
                                         ('move', element.etree_element))

    def do_display(self, element, value):
        """Implement display, esp. wrapping of content."""
        debug(element.local_name, 'display', serialize(value))
        # This is where we create the wrapping element, then stuff it in the
        # state
        disp_value = serialize(value).strip()
        if len(self.state['pending_elems']) > 0:
            if self.state['pending_elems'][-1][1] == element:  # do_content
                if 'block' in disp_value:
                    pass
                else:
                    elem = self.state['pending_elems'][-1][0]
                    if elem.tag != 'span':
                        elem.tag = 'span'
        else:
            if 'block' in disp_value:
                elem = etree.Element('div')
                elem.set('data-type', 'composite-page')
            else:
                elem = etree.Element('span')
            self.state['pending_elems'].append((elem, element))
            return self.pop_pending_elem

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if len(self.state['pending_elems']) > 0:
            if self.state['pending_elems'][-1][1] == element:
                self.state['pending_elems'].pop()

    def do_content(self, element, value):
        """Implement content declaration - pre-match."""
        debug(element.local_name, 'content', serialize(value))
        retval = None

        if 'pending(' in serialize(value):
            target = extract_pending_target(value)
            if len(self.state['pending_elems']) > 0 \
                    and self.state['pending_elems'][-1][1] == element:

                elem = self.state['pending_elems'][-1][0]
            else:
                elem = etree.Element('div')
                elem.set('data-type', 'composite-page')
                self.state['pending_elems'].append((elem, element))
                retval = self.pop_pending_elem

            self.state['pending'].setdefault(target, []).append(
                                             ('target', element.etree_element))
            self.state['pending'].setdefault(target, []).append(
                                             ('move', elem))
            self.state['pending'].setdefault(target, []).append(
                                             ('target', elem))
        return retval

    def do_pending(self, element, value):
        """Implement pending content move/copy."""
        pass

    def do_class(self, element, value):
        """Implement class declaration - pre-match."""
        debug(element.local_name, 'class', serialize(value))
        if is_pending_element(self.state, element):
            elem = self.state['pending_elems'][-1][0]
            elem.set('class', serialize(value).strip())

        else:  # it's not there yet, perhaps after
            return functools.partial(self.do_class, value=value)

    def do_group_by(self, element, value):
        """Implement group-by declaration - pre-match."""
        debug(element.local_name, 'group-by', serialize(value))

    def do_sort_by(self, element, value):
        """Implement sort-by declaration - pre-match."""
        debug(element.local_name, 'sort-by', serialize(value))


def extract_pending_target(value):
    """Return the unicode value of the first pending() content function."""
    for v in value:
        if type(v) is tinycss2.ast.FunctionBlock:
            if v.name == u'pending':
                return serialize(v.arguments)


def is_pending_element(state, element):
    """Determine if most recent pending is for this element."""
    return len(state['pending_elems']) > 0 \
        and state['pending_elems'][-1][1] == element


def is_collation_rule(rule):
    """A collation rule contains a declaration needed to complete collation."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    return any([d.name == dn and dv in serialize(d.value)
                for dn, dv in collation_decls
                for d in declarations])


def is_numbering_rule(rule):
    """A numbering rule contains a declaration needed to complete numbering."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    return any([d.name == dn and dv in serialize(d.value)
                for dn, dv in numbering_decls
                for d in declarations])


def match(root, matcher):
    """Test matching."""
    pending = []
    for element in ElementWrapper.from_html_root(root).iter_subtree():
        for rule in matcher.match(element):
            pending.append((element, rule))
    debug(len(pending))


def debug(*args, **kwargs):
    """Wrapped print for verbose output to stderr."""
    if verbose:
        print(*args, file=sys.stderr, **kwargs)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Process raw HTML to cooked"
                                                 " (embedded numbering and"
                                                 " collation)")
    parser.add_argument("css_rules",
                        type=argparse.FileType('r'),
                        help="CSS3 ruleset stylesheet recipe")
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
    args = parser.parse_args()
    verbose = args.verbose
    main(args.css_rules, args.html_in, args.html_out)
