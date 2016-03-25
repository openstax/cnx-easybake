#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list
import cssselect2
from cssselect2 import ElementWrapper
import copy

verbose = False

# steps = ('collation', 'numbering', 'labelling')
steps = ('collation',)
decls = {'collation': [(u'move-to', ''),
                       (u'copy-to', ''),
                       (u'content', u'pending')],
         'numbering': [(u'string-set', ''),
                       (u'class', ''),
                       (u'content', u'string')],
         'labelling': [(u'counter-reset', ''),
                       (u'counter-increment', ''),
                       (u'content', u'counter'),
                       (u'content', u'target-counter')]
         }

logger = logging.getLogger('cnx-easybake')


class Oven():
    """Collate and number HTML with CSS3.

    An object that parses and stores rules defined in CSS3 and can apply
    them to an HTML file.
    """

    def __init__(self, css_in=None):
        """Initialize oven, with optional inital CSS."""
        if css_in:
            self.update_css(css_in, clear_css=True)  # clears state as well
        else:
            self.clear_state()

    def clear_state(self):
        """Clear the recipe state."""
        self.state = {}
        for step in steps:
            self.state[step] = {}
            self.state[step]['pending'] = {}
            self.state[step]['actions'] = []
            self.state[step]['pending_elems'] = []
            self.state[step]['counters'] = {}
            self.state[step]['strings'] = {}
            # FIXME rather than boolean should ref HTML tree
            self.state[step]['recipe'] = False

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
            self.matchers = {}
            for step in steps:
                self.matchers[step] = cssselect2.Matcher()

        rules, _ = tinycss2.parse_stylesheet_bytes(css, skip_whitespace=True)
        for rule in rules:
            # Ignore all at-rules FIXME probably need @counters
            if rule.type == 'qualified-rule':
                try:
                    selectors = cssselect2.compile_selector_list(rule.prelude)
                except cssselect2.SelectorError as error:
                    logger.debug('Invalid selector: %s %s'
                                 % (serialize(rule.prelude), error))
                else:
                    step = rule_step(rule)
                    if step in steps:
                        decls = parse_declaration_list(rule.content,
                                                       skip_whitespace=True)
                        for sel in selectors:
                            pseudo = sel.pseudo_element
                            self.matchers[step].add_selector(sel,
                                                             (decls, pseudo))

    def bake(self, element):
        """Apply recipes to HTML tree. Will build recipes if needed."""
        wrapped_html_tree = ElementWrapper.from_html_root(element)
        for step in steps:
            # loop over steps, collation, then numbering, then labelling

            if not self.state[step]['recipe']:
                recipe = self.build_recipe(wrapped_html_tree, step)
            else:
                recipe = self.state[step]

            target = None
            for action, value in recipe['actions']:
                if action == 'target':
                    target = value
                elif action == 'move':
                    target.append(value)
                elif action == 'copy':
                    target.append(copy.deepcopy(value))

        # Do numbering

        # Do label/link updates

    def build_recipe(self, element, step, depth=0):
        """Construct a set of steps to collate (and number) an HTML doc.

        Returns a state object that contains the steps to apply to the HTML
        tree. CSS rules match during a recusive descent HTML tree walk. Each
        declaration has a method that then runs, given the current element, the
        decaration value. State is maintained on the collator instance.  Since
        matching occurs when entering a node, declaration methods are ran
        either before or after recursing into its children, depending on the
        presence of a pseudo-element and it's value.
        """
        # FIXME Do declaration methods need to know if they are pseudo or not,
        # and if so, which? - currently passing it, but not using it.

        matching_rules = {}
        for declarations, pseudo in self.matchers[step].match(element):
            matching_rules.setdefault(pseudo, []).append(declarations)

        # Do before
        if 'before' in matching_rules:
            for declarations in matching_rules.get('before'):
                # pseudo element, create wrapper
                self.push_pending_elem(element)
                for decl in declarations:
                    method = self.find_method(decl.name)
                    method(element, decl, 'before')
                # deal w/ pending_elements, per rule
                self.pop_pending_elem(element)

        # Do non-pseudo
        if None in matching_rules:
            for declarations in matching_rules.get(None):
                for decl in declarations:
                    method = self.find_method(decl.name)
                    method(element, decl, None)

        # Recurse
        for el in element.iter_children():
            _state = self.build_recipe(el, step, depth=depth+1)  # noqa

        # Do after
        if 'after' in matching_rules:
            for declarations in matching_rules.get('after'):
                # pseudo element, create wrapper
                self.push_pending_elem(element)
                for decl in declarations:
                    method = self.find_method(decl.name)
                    method(element, decl, 'after')
                # deal w/ pending_elements, per rule
                self.pop_pending_elem(element)

        if depth == 0:
            self.state[step]['recipe'] = True  # FIXME should ref HTML tree
        return self.state[step]

    def find_method(self, name):
        """Find class method to call for declaration based on name."""
        method = None
        try:
            method = getattr(self, 'do_{}'.format(
                             (name).replace('-', '_')))
        except AttributeError:
            try:
                if name.startswith('data-'):
                    method = getattr(self, 'do_data_any')
                elif name.startswith('attr-'):
                    method = getattr(self, 'do_attr_any')
                else:
                    logger.debug('Missing method {}'.format(
                                     (name).replace('-', '_')))
            except AttributeError:
                logger.debug('Missing method {}'.format(
                                 (name).replace('-', '_')))
        if method:
            return method
        else:
            return lambda x, y, z: None

    def do_copy_to(self, element, decl, pseudo):
        """Implement copy-to declaration - pre-match."""
        target = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'copy-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.state['collation']['pending_elems'][-1][1] == element:
            elem = self.state['collation']['pending_elems'][-1][0]
        self.state['collation']['pending'].setdefault(target, []).append(
                                         ('copy', elem))

    def do_move_to(self, element, decl, pseudo):
        """Implement move-to declaration - pre-match."""
        target = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'move-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.state['collation']['pending_elems'][-1][1] == element:
            elem = self.state['collation']['pending_elems'][-1][0]
        self.state['collation']['pending'].setdefault(target, []).append(
                             ('move', elem))

    def do_container(self, element, decl, pseudo):
        """Implement display, esp. wrapping of content."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'container', value))
        if is_pending_element(self.state, element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.tag = value

    def do_attr_any(self, element, decl, pseudo):
        """Implement generic attribute setting."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, decl.name, value))
        if is_pending_element(self.state, element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set(decl.name[5:], value)

    def do_data_any(self, element, decl, pseudo):
        """Implement generic data attribute setting."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, decl.name, value))
        if is_pending_element(self.state, element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set(decl.name, value)

    def do_content(self, element, decl, pseudo):
        """Implement content declaration - after."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'content', value))

        if 'pending(' in value:  # FIXME need to handle multi-param values
            target = extract_pending_target(decl.value)
            if is_pending_element(self.state, element):
                elem = self.state['collation']['pending_elems'][-1][0]
            else:
                elem = etree.Element('div')
                self.state['collation']['pending_elems'].append(
                                                         (elem, element))

            self.state['collation']['actions'].append(
                                             ('target', element.etree_element))
            self.state['collation']['actions'].append(('move', elem))
            self.state['collation']['actions'].append(('target', elem))
            self.state['collation']['actions'].extend(
                                    self.state['collation']['pending'][target])
            del self.state['collation']['pending'][target]

    def push_pending_elem(self, element):
        """Remove pending target element from stack."""
        elem = etree.Element('div')
        self.state['collation']['pending_elems'].append(
                                                 (elem, element))

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if len(self.state['collation']['pending_elems']) > 0:
            if self.state['collation']['pending_elems'][-1][1] == element:
                self.state['collation']['pending_elems'].pop()

    def do_class(self, element, decl, pseudo):
        """Implement class declaration - pre-match."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'class', value))
        if is_pending_element(self.state, element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set('class', value)

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
    return len(state['collation']['pending_elems']) > 0 \
        and state['collation']['pending_elems'][-1][1] == element


def rule_step(rule):
    """A collation rule contains a declaration needed to complete collation."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    for step in steps:
        if any([d.name == dn and dv in serialize(d.value)
                for dn, dv in decls[step]
                for d in declarations]):
            return step
    return 'unknown'
