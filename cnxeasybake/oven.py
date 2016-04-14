#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list, ast
import cssselect2
from cssselect2 import ElementWrapper
from cssselect import HTMLTranslator
import copy

verbose = False

# steps = ('collation', 'numbering', 'labelling')
steps = ('collation',)
decls = {'collation': [(u'move-to', ''),
                       (u'copy-to', ''),
                       (u'string-set', ''),
                       (u'node-set', ''),
                       (u'content', u'string'),
                       (u'content', u'nodes'),
                       (u'content', u'pending')],
         'numbering': [(u'counter-reset', ''),
                       (u'counter-increment', ''),
                       (u'content', u'counter'),
                       (u'content', u'target-counter')],
         'labelling': [(u'string-set', ''),
                       (u'class', ''),
                       (u'content', u'string')],
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
            self.matchers = {}
            for step in steps:
                self.matchers[step] = cssselect2.Matcher()

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
            old_content = {}
            sort = None
            for action, value in recipe['actions']:
                if action == 'target':
                    target, location, sort = value
                    old_content = {}
                elif action == 'clear':
                    old_content['text'] = target.text
                    target.text = None
                    old_content['children'] = []
                    for child in target:
                        old_content['children'].append(child)
                        target.remove(child)
                elif action == 'content':
                    if old_content:
                        append_string(target, old_content['text'])
                        for child in old_content['children']:
                            target.append(child)
                elif action == 'string':
                    if location == 'before':
                        prepend_string(target, value)
                    else:
                        append_string(target, value)
                elif action == 'move':
                    if sort and len(target) > 0:
                        for child in target:
                            if sort(child) > sort(value):
                                break
                        child.addprevious(value)
                    else:
                        if location == 'before':
                            value.tail = target.text
                            target.text = None
                            target.insert(0, value)
                        else:
                            target.append(value)
                elif action == 'copy':
                    mycopy = copy.deepcopy(value)  # FIXME deal w/ ID values
                    mycopy.tail = None
                    if sort and len(target) > 0:
                        for child in target:
                            if sort(child) > sort(value):
                                break
                        child.addprevious(mycopy)
                    else:
                        if location == 'before':
                            mycopy.tail = target.text
                            target.text = None
                            target.insert(0, mycopy)
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
                    logger.warning('Missing method {}'.format(
                                     (name).replace('-', '_')))
            except AttributeError:
                logger.warning('Missing method {}'.format(
                                 (name).replace('-', '_')))
        if method:
            return method
        else:
            return lambda x, y, z: None

    def do_string_set(self, element, decl, pseudo):
        """Implement string-set declaration."""
        args = serialize(decl.value)
        logger.debug("{} {} {}".format(
                     element.local_name, 'string-set', args))
        step = self.state['collation']
        strval = ''
        strname = None
        for term in decl.value:
            if type(term) is ast.WhitespaceToken:
                continue

            elif type(term) is ast.StringToken:
                if strname is not None:
                    strval += term.value
                else:
                    logger.warning("Bad string-set: {}".format(args))

            elif type(term) is ast.IdentToken:
                if strname is not None:
                    logger.warning("Bad string-set: {}".format(args))
                else:
                    strname = term.value

            elif type(term) is ast.LiteralToken:
                if strname is None:
                    logger.warning("Bad string-set: {}".format(args))
                else:
                    step['strings'][strname] = strval
                    strval = ''
                    strname = None

            elif type(term) is ast.FunctionBlock:
                if term.name == 'string':
                    other_strname = serialize(term.arguments)
                    if other_strname not in step['strings']:
                        logger.warning("{} blank string".
                                       format(strname))
                        continue
                    if strname is not None:
                        strval += step['strings'][other_strname]
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == u'attr':
                    if strname is not None:
                        att_name = serialize(term.arguments)
                        strval += element.etree_element.get(att_name, '')
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == u'content':
                    if strname is not None:
                        att_name = serialize(term.arguments)
                        strval += element.etree_element.xpath('./text()')[0]
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == u'pending':
                    logger.warning("Bad string-set:pending() not allowed. {}".
                                   format(args))

        if strname is not None:
            step['strings'][strname] = strval

    def do_node_set(self, element, decl, pseudo):
        """Implement node-set declaration."""
        target = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'node-set', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = self.state['collation']['pending_elems'][-1][0]
        self.state['collation']['pending'][target] = [('copy', elem)]

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
        # Need: content() string(x) attr(x) link(id)
        #
        value = serialize(decl.value).strip()
        logger.debug("{} {} {}".format(
                     element.local_name, 'content', value))

        step = self.state['collation']
        actions = step['actions']

        elem = None
        if self.is_pending_element(element):
            elem, _, sort = step['pending_elems'][-1]

        actions.append(('target', (element.etree_element, pseudo, None)))
        if self.is_pending_element(element):
            actions.append(('move', elem))
            actions.append(('target', (elem, None, sort)))
        else:
            actions.append(('clear', elem))

        # decl.value is parsed representation: loop over it
        # if a string, to pending elem - either text, or tail of last child
        # if a string(x) retrieve value from state and attach as tail
        # if a pending(x), do the target/extend dance
        # content() attr(x), link(x,y) etc.
        for term in decl.value:
            if type(term) is ast.WhitespaceToken:
                continue

            elif type(term) is ast.StringToken:
                actions.append(('string', term.value))

            elif type(term) is ast.FunctionBlock:
                if term.name == 'string':
                    strname = serialize(term.arguments)
                    if strname not in step['strings']:
                        logger.warning("{} blank string".
                                       format(strname))
                        continue
                    actions.append(('string', step['strings'][strname]))

                elif term.name == u'attr':
                    att_name = serialize(term.arguments)
                    actions.append(('string',
                                    element.etree_element.get(att_name, '')))

                elif term.name == u'content':
                    actions.append(('content', None))

                elif term.name in ('nodes', 'pending'):
                    target = serialize(term.arguments)
                    if target not in step['pending']:
                        logger.warning("{} empty bucket".
                                       format(target))
                        continue
                    actions.extend(step['pending'][target])
                    if term.name == u'pending':
                        del step['pending'][target]
                else:
                    logger.warning("Unknown function {}".
                                   format(term.name))
            else:
                logger.warning("Unknown term {}".
                               format(decl.value))

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
                    self.state['collation']['actions'][target_index] = \
                        (action[0], (action[1][0], None, sort))


def append_string(node, string):
    """Append a string to a node, as text or tail of last child."""
    if string:
        if len(node) == 0:
            if node.text is not None:
                node.text += string
            else:
                node.text = string
        else:  # Get last child
            child = list(node)[-1]
            if child.tail is not None:
                child.tail += string
            else:
                child.tail = string


def prepend_string(node, string):
    """Prepend a string to a node as text."""
    if node.text is not None:
        node.text += string
    else:
        node.text = string


def rule_step(rule):
    """A collation rule contains a declaration needed to complete collation."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    for step in steps:
        if any([d.name == dn and dv in serialize(d.value)
                for dn, dv in decls[step]
                for d in declarations]):
            return step
    return 'unknown'
