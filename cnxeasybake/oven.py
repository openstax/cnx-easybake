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
            self.state[step]['actions'] = {}
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

    def build_recipe(self, element, step, depth=0):
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

        for declarations, pseudo in self.matchers[step].match(element):
            if pseudo in (None, 'before'):
                for decl in declarations:
                    try:
                        method = getattr(self, 'do_{}'.format(
                                         (decl.name).replace('-', '_')))
                        method(element, decl.value, pseudo)
                    except AttributeError:
                        logger.debug('Missing method {}'.format(
                                         (decl.name).replace('-', '_')))
            # deal w/ pending_elements, per rule
            self.pop_pending_elem(element)

        for el in element.iter_children():
            _state = self.build_recipe(el, step, depth=depth+1)  # noqa

        # FIXME don't run matcher twice!!!

        for declarations, pseudo in self.matchers[step].match(element):
            if pseudo == 'after':
                for decl in declarations:
                    try:
                        method = getattr(self, 'do_{}'.format(
                                         (decl.name).replace('-', '_')))
                        method(element, decl.value, pseudo)
                    except AttributeError:
                        logger.debug('Missing method {}'.format(
                                         (decl.name).replace('-', '_')))
            # deal w/ pending_elements, per rule
            self.pop_pending_elem(element)

        if depth == 0:
            self.state[step]['recipe'] = True  # FIXME should ref HTML tree
        return self.state[step]

    def do_copy_to(self, element, value, pseudo):
        """Implement copy-to declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'copy-to', serialize(value)))
        target = serialize(value).strip()
        self.state['collation']['pending'].setdefault(target, []).append(
                                         ('copy', element.etree_element))

    def do_move_to(self, element, value, pseudo):
        """Implement move-to declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'move-to', serialize(value)))
        target = serialize(value).strip()
        self.state['collation']['pending'].setdefault(target, []).append(
                                         ('move', element.etree_element))

    def do_display(self, element, value, pseduo):
        """Implement display, esp. wrapping of content."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'display', serialize(value)))
        # This is where we create the wrapping element, then stuff it in the
        # state
        disp_value = serialize(value).strip()
        if len(self.state['collation']['pending_elems']) > 0:
            if self.state['collation']['pending_elems'][-1][1] == element:
                if 'block' in disp_value:
                    pass
                else:
                    elem = self.state['collation']['pending_elems'][-1][0]
                    if elem.tag != 'span':
                        elem.tag = 'span'
        else:
            if 'block' in disp_value:
                elem = etree.Element('div')
                elem.set('data-type', 'composite-page')
            else:
                elem = etree.Element('span')
            self.state['collation']['pending_elems'].append((elem, element))
            return self.pop_pending_elem

    def do_content(self, element, value, pseudo):
        """Implement content declaration - after."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'content', serialize(value)))
        retval = None

        if 'pending(' in serialize(value):
            target = extract_pending_target(value)
            if len(self.state['collation']['pending_elems']) > 0 \
                    and \
                    self.state['collation']['pending_elems'][-1][1] == element:

                elem = self.state['collation']['pending_elems'][-1][0]
            else:
                elem = etree.Element('div')
                elem.set('data-type', 'composite-page')
                self.state['collation']['pending_elems'].append(
                                                         (elem, element))
                retval = self.pop_pending_elem

            self.state['collation']['actions'].setdefault(target, []).append(
                                             ('target', element.etree_element))
            self.state['collation']['actions'][target].append(('move', elem))
            self.state['collation']['actions'][target].append(('target', elem))
            self.state['collation']['actions'][target].extend(
                                    self.state['collation']['pending'][target])
            del self.state['collation']['pending'][target]

        return retval

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if len(self.state['collation']['pending_elems']) > 0:
            if self.state['collation']['pending_elems'][-1][1] == element:
                self.state['collation']['pending_elems'].pop()

    def do_class(self, element, value, pseudo):
        """Implement class declaration - pre-match."""
        logger.debug("{} {} {}".format(
                     element.local_name, 'class', serialize(value)))
        if is_pending_element(self.state, element):
            elem = self.state['collation']['pending_elems'][-1][0]
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
