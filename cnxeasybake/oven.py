#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list
import cssselect2
from cssselect2 import ElementWrapper
from cssselect import HTMLTranslator
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
        # loop over steps: collation, then numbering, then labelling
        for step in steps:
            # Need to wrap each loop, since tree may have changed
            wrapped_html_tree = ElementWrapper.from_html_root(element)

            if not self.state[step]['recipe']:
                recipe = self.build_recipe(wrapped_html_tree, step)
            else:
                recipe = self.state[step]

            target = None
            sort = None
            for action, value in recipe['actions']:
                if action == 'target':
                    target, sort = value
                elif action == 'move':
                    if sort and len(target) > 0:
                        for child in target:
                            if sort(child) > sort(value):
                                break
                        child.addprevious(value)
                    else:
                        target.append(value)
                elif action == 'copy':
                    mycopy = copy.deepcopy(value)  # FIXME deal w/ ID values
                    if sort and len(target) > 0:
                        for child in target:
                            if sort(child) > sort(value):
                                break
                        child.addprevious(mycopy)
                    else:
                        target.append(mycopy)

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

    # Maintain stack of pending wrapper elements
    def push_pending_elem(self, element):
        """Create and place pending target element onto stack."""
        elem = etree.Element('div')
        self.state['collation']['pending_elems'].append(
                                                 (elem, element, None))

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if self.is_pending_element(element):
            self.state['collation']['pending_elems'].pop()

    def is_pending_element(self, element):
        """Determine if most recent pending is for this element."""
        return len(self.state['collation']['pending_elems']) > 0 \
            and self.state['collation']['pending_elems'][-1][1] == element

    # Declaration methods and accessor
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
        """Implement copy-to declaration."""
        target = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'copy-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
        self.state['collation']['pending'].setdefault(target, []).append(
                                         ('copy', elem))

    def do_move_to(self, element, decl, pseudo):
        """Implement move-to declaration."""
        target = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'move-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
        self.state['collation']['pending'].setdefault(target, []).append(
                             ('move', elem))

    def do_container(self, element, decl, pseudo):
        """Implement setting tag for new wrapper element."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'container', value))
        if self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.tag = value

    def do_class(self, element, decl, pseudo):
        """Implement class declaration - pre-match."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'class', value))
        if self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set('class', value)

    def do_attr_any(self, element, decl, pseudo):
        """Implement generic attribute setting on new wrapper element."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, decl.name, value))
        if self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set(decl.name[5:], value)

    def do_data_any(self, element, decl, pseudo):
        """Implement generic data attribute setting on new wrapper element."""
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, decl.name, value))
        if self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
            elem.set(decl.name, value)

    def do_content(self, element, decl, pseudo):
        """Implement content declaration."""
        # FIXME rework completely to cover all cases, pseudo and non-
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'content', value))

        step = self.state['collation']
        actions = step['actions']

        if 'pending(' in value:  # FIXME need to handle multi-param values
            target = extract_pending_target(decl.value)
            if target not in step['pending']:
                logger.warning("WARNING: {} empty bucket".format(value))
                return

            if self.is_pending_element(element):
                elem, _, sort = step['pending_elems'][-1]
            actions.append(('target', (element.etree_element, None)))
            actions.append(('move', elem))
            actions.append(('target', (elem, sort)))
            actions.extend(step['pending'][target])
            del step['pending'][target]

    def do_group_by(self, element, decl, pseudo):
        """Implement group-by declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'group-by', serialize(decl.value)))

    def do_sort_by(self, element, decl, pseudo):
        """Implement sort-by declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'sort-by', serialize(decl.value)))

        css = serialize(decl.value)
        sort = etree.XPath(HTMLTranslator().css_to_xpath(css) + '/text()')

        if self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
            self.state['collation']['pending_elems'][-1] = \
                (elem, element, sort)
            #  Find current target, set its sort as well
            for pos, action in \
                    enumerate(reversed(self.state['collation']['actions'])):
                if action[0] == 'target' and action[1][0] == elem:
                    target_index = - pos - 1
                    break
            self.state['collation']['actions'][target_index] = \
                (action[0], (action[1][0], sort))


def extract_pending_target(value):
    """Return the unicode value of the first pending() content function."""
    for v in value:
        if type(v) is tinycss2.ast.FunctionBlock:
            if v.name == u'pending':
                return serialize(v.arguments)


def rule_step(rule):
    """A collation rule contains a declaration needed to complete collation."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    for step in steps:
        if any([d.name == dn and dv in serialize(d.value)
                for dn, dv in decls[step]
                for d in declarations]):
            return step
    return 'unknown'
