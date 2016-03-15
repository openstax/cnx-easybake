#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list
import cssselect2
from cssselect2 import ElementWrapper
import functools
import copy

verbose = False
collation_decls = [(u'move-to', ''),
                   (u'copy-to', ''),
                   (u'content', u'pending')]

labeling_decls = [(u'string-set', ''),
                  (u'class', '')]

numbering_decls = [(u'counter-reset', ''),
                   (u'counter-increment', ''),
                   (u'content', u'counter'),
                   (u'content', u'target-counter')]

logger = logging.getLogger('cnx-easybake')


class Oven():
    """Collate and number HTML with CSS3.

    An object that parses and stores rules defined in CSS3 and can apply
    them to an HTML file.
    """

    def __init__(self, css_in=None):
        """Initialize oven, with optional inital CSS."""
        matcher = cssselect2.Matcher()
        self.matcher = matcher
        if css_in:
            self.update_css(css_in)  # clears state as well
        else:
            self.clear_state()

    def clear_state(self):
        """Clear the recipe state."""
        self.state = {}
        self.state['pending'] = {}
        self.state['actions'] = {}
        self.state['pending_elems'] = []
        self.state['counters'] = {}
        self.state['strings'] = {}
        self.state['recipe'] = False

    def update_css(self, css_in=None, clear_css=False):
        """Add additional CSS rules, optionally replacing all."""
        if css_in is None:
            return
        try:
            with open(css_in) as f:  # is it a path/filename?
                css = f.read()
        except (IOError, TypeError):
            try:
                css = css_in.read()  # Perhaps a file obj?
            except AttributeError:
                css = css_in         # Treat it as a string

        # always clears state, since rules have changed
        self.clear_state()

        if clear_css:
            self.matcher = cssselect2.Matcher()

        rules, _ = tinycss2.parse_stylesheet_bytes(css, skip_whitespace=True)
        for rule in rules:
            # Ignore all at-rules
            if rule.type == 'qualified-rule':
                try:
                    selectors = cssselect2.compile_selector_list(rule.prelude)
                except cssselect2.SelectorError as error:
                    logger.debug('Invalid selector: %s %s'
                                 % (serialize(rule.prelude), error))
                else:
                    if is_collation_rule(rule):
                        decls = parse_declaration_list(rule.content,
                                                       skip_whitespace=True)
                        for sel in selectors:
                            pseudo = sel.pseudo_element
                            self.matcher.add_selector(sel, (decls, pseudo))

    def bake(self, element):
        """Apply recipe to HTML tree. Will build recipe if needed."""
        wrapped_html_tree = ElementWrapper.from_html_root(element)
        if not self.state['recipe']:
            recipe = self.build_recipe(wrapped_html_tree)
        else:
            recipe = self.state

        # loop over pending dictionaries, doing moves and copies to etree

        for key, actions in recipe['actions'].iteritems():
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

    def build_recipe(self, element, depth=0):
        """Construct a set of steps to collate (and number) an HTML doc.

        Returns a state object that contains the steps. CSS rules match during
        a recusive descent HTML tree walk. Each declaration has a method that
        then runs, given the current element, the decaration value. State is
        maintained on the collator instance.  Since matching occurs when
        entering a node, it's children have not yet been visited, so each
        declaration method can optionally return a deferred method to run when
        the current node's children have been processed.
        """
        # FIXME  Extending to deal with pseudo elements now match also return
        # pseudo, which will be one of None, before, or after.  Need after
        # declaration methods will fire _after_ recursing to children.  Move
        # 'pending' actions in state to 'actions' move-to, copy-to push things
        # to 'pending' dict.  pending() on content then moves that to 'actions'
        # with appropriate 'target' steps prepended.
        # FIXME Do declaration methods need to know if they are pseudo or not,
        # and if so, which?

        # FIXME  deal w/ order of execution of content: pending() and
        # class|display - keep a local node pointer somewhere, or pending
        # actions so only pending() does the create-a-node?

        # FIXME remove the method returning something to fire after child
        # processing Think it's a YAGNI - current use by class won't survive

        for declarations, pseudo in self.matcher.match(element):
            if pseudo in (None, 'before'):
                for decl in declarations:
                    method = getattr(self, 'do_{}'.format(
                                     (decl.name).replace('-', '_')))
                    method(element, decl.value, pseudo)

        for el in element.iter_children():
            _state = self.build_recipe(el, depth=depth+1)  # noqa

        # FIXME don't run matcher twice!!!

        for declarations, pseudo in self.matcher.match(element):
            if pseudo == 'after':
                for decl in declarations:
                    method = getattr(self, 'do_{}'.format(
                                     (decl.name).replace('-', '_')))
                    method(element, decl.value, pseudo)

        self.state['recipe'] = True
        return self.state

    def do_copy_to(self, element, value, pseudo):
        """Implement copy-to declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'copy-to', serialize(value)))
        target = serialize(value).strip()
        self.state['pending'].setdefault(target, []).append(
                                         ('copy', element.etree_element))

    def do_move_to(self, element, value, pseudo):
        """Implement move-to declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'move-to', serialize(value)))
        target = serialize(value).strip()
        self.state['pending'].setdefault(target, []).append(
                                         ('move', element.etree_element))

    def do_display(self, element, value, pseduo):
        """Implement display, esp. wrapping of content."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'display', serialize(value)))
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

    def do_content(self, element, value, pseudo):
        """Implement content declaration - after."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'content', serialize(value)))
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

            self.state['actions'].setdefault(target, []).append(
                                             ('target', element.etree_element))
            self.state['actions'][target].append(('move', elem))
            self.state['actions'][target].append(('target', elem))
            self.state['actions'][target].extend(self.state['pending'][target])
            del self.state['pending'][target]

        return retval

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if len(self.state['pending_elems']) > 0:
            if self.state['pending_elems'][-1][1] == element:
                self.state['pending_elems'].pop()

    def do_class(self, element, value, pseudo):
        """Implement class declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'class', serialize(value)))
        if is_pending_element(self.state, element):
            elem = self.state['pending_elems'][-1][0]
            elem.set('class', serialize(value).strip())

        else:  # it's not there yet, perhaps after
            return functools.partial(self.do_class, value=value)

    def do_group_by(self, element, value, pseudo):
        """Implement group-by declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'group-by', serialize(value)))

    def do_sort_by(self, element, value, pseudo):
        """Implement sort-by declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'sort-by', serialize(value)))


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
