#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list, ast
import cssselect2
from cssselect2 import ElementWrapper
from cssselect2.parser import parse
from cssselect2.compiler import CompiledSelector
from cssselect2.extensions import extensions
from copy import deepcopy
from icu import Locale, Collator, UnicodeString
from uuid import uuid4

from . import css, expr, util


verbose = False

logger = logging.getLogger('cnx-easybake')


def prefixify(tag):
    return '{http://www.w3.org/1999/xhtml}' + tag


SELF_CLOSING_TAGS = list(map(prefixify, ['area', 'base', 'br', 'col',
                                         'command', 'embed', 'hr', 'img',
                                         'input', 'keygen', 'link', 'meta',
                                         'param', 'source', 'track', 'wbr']))


def log_decl_method(func):
    """Decorate do_declartion methods for debug logging."""
    from functools import wraps

    @wraps(func)
    def with_logging(*args, **kwargs):
        self = args[0]
        decl = args[2]
        logger.debug(u"    {}: {} {}".format(self.state['current_step'],
                     decl.name, serialize(decl.value).strip()).encode('utf-8'))
        return func(*args, **kwargs)
    return with_logging


class Target():
    """Represent the target for a move or copy."""

    def __init__(self, tree, location=None, parent=None,
                 sort=None, isgroup=False, groupby=None, lang=None):
        """Set up target object."""
        self.tree = tree
        self.location = location
        self.parent = parent
        self.sort = sort
        self.isgroup = isgroup
        self.groupby = groupby
        self.lang = lang

    def __str__(self):
        """Return string."""
        return (u"tree: {0.tree} "
                u"location: {0.location} "
                u"sort: {0.sort} "
                u"isgroup: {0.isgroup} "
                u"groupby: {0.groupby}".format(self))


class Oven():
    """Collate and number HTML with CSS3.

    An object that parses and stores rules defined in CSS3 and can apply
    them to an HTML file.
    """

    def __init__(self, css_in=None, use_repeatable_ids=False):
        """Initialize oven, with optional inital CSS."""
        self.coverage_lines = []
        self.use_repeatable_ids = use_repeatable_ids
        self.repeatable_id_counter = 0
        # Store the CSS namespaces (and prefixed namespaces)
        self.css_namespaces = {}

        if css_in:
            self.update_css(css_in, clear_css=True)  # clears state as well
        else:
            self.matchers = {}
            self.clear_state()

    def generate_id(self):
        """Generate a fresh id"""
        if self.use_repeatable_ids:
            self.repeatable_id_counter += 1
            return 'autobaked-{}'.format(self.repeatable_id_counter)
        else:
            return str(uuid4())

    def clear_state(self):
        """Clear the recipe state."""
        self.state = {}
        self.state['steps'] = []
        self.state['current_step'] = None
        self.state['scope'] = []
        self.state['counters'] = {}
        self.state['strings'] = {}
        for step in self.matchers:
            self.state[step] = {}
            self.state[step]['pending'] = {}
            self.state[step]['actions'] = []
            self.state[step]['counters'] = {}
            self.state[step]['strings'] = {}
            # FIXME rather than boolean should ref HTML tree
            self.state[step]['recipe'] = False

    def update_css(self, css_in=None, clear_css=False):
        """Add additional CSS rules, optionally replacing all."""
        if clear_css:
            self.matchers = {}

        # CSS is changing, so clear processing state
        self.clear_state()

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

        # Namespaces defined in the CSS
        if clear_css:
            self.css_namespaces = {}

        rules, _ = tinycss2.parse_stylesheet_bytes(css, skip_whitespace=True)
        for rule in rules:
            # Check for any @namespace declarations
            if rule.type == 'at-rule':
                if rule.lower_at_keyword == 'namespace':
                    # The 1 supported format is:
                    #
                    # default (unsupported):  [<WhitespaceToken>,
                    #            <StringToken "http://www.w3.org/1999/xhtml">]
                    # prefixed: [<WhitespaceToken>,
                    #            <IdentToken html>,
                    #            <WhitespaceToken>,
                    #            <StringToken "http://www.w3.org/1999/xhtml">]
                    if len(rule.prelude) == 4 and \
                           [tok.type for tok in rule.prelude] == \
                           ['whitespace', 'ident', 'whitespace', 'string']:

                        # Prefixed namespace
                        ns_prefix = rule.prelude[1].value
                        ns_url = rule.prelude[3].value
                        self.css_namespaces[ns_prefix] = ns_url
                    else:
                        # etree.XPath does not support the default namespace
                        # and XPath is used to implement `sort-by:`
                        # http://www.goodmami.org/2015/11/04/
                        # ... python-xpath-and-default-namespaces.html
                        logger.warning(u'Unknown @namespace format at {}:{}'
                                       .format(rule.source_line,
                                               rule.source_column)
                                       .encode('utf-8'))

            elif rule.type == 'qualified-rule':

                selectors = parse(rule.prelude, namespaces=self.css_namespaces,
                                  extensions=extensions)
                decls = [d for d in
                         parse_declaration_list(rule.content,
                                                skip_whitespace=True)
                         if d.type == 'declaration']  # Could also be a comment
                for sel in selectors:
                    try:
                        csel = CompiledSelector(sel)
                    except cssselect2.SelectorError as error:
                        logger.warning(u'Invalid selector: {} {}'.format(
                            serialize(rule.prelude), error).encode('utf-8'))
                    else:
                        steps, extras = extract_selector_info(sel)
                        label = csel.pseudo_element
                        if len(extras) > 0:
                            if label is not None:
                                extras.insert(0, label)
                            label = '_'.join(extras)

                        for step in steps:
                            if step not in self.matchers:
                                self.matchers[step] = cssselect2.Matcher()
                            self.record_coverage_zero(rule,
                                                      sel.source_line_offset)
                            self.matchers[step].add_selector(
                                 csel,
                                 ((rule.source_line + sel.source_line_offset,
                                   serialize(rule.prelude).replace('\n', ' ')),
                                  decls, label))
            elif rule.type == 'comment':
                pass
            elif rule.type == 'error':
                logger.error(u'Parse Error {}: {}'.format(
                    rule.kind, rule.message).encode('utf-8'))
                # Phil does not know how to nicely exit with staus != 0
                raise ValueError(u'Parse Error {}: {}'.format(
                    rule.kind, rule.message).encode('utf-8'))
            else:
                raise ValueError(u'BUG: Unknown ruletype={}'.format(rule.type))

        steps = sorted(self.matchers.keys())
        if len(steps) > 1:
            if 'default' in steps:
                steps.remove('default')
                try:
                    steps.sort(key=int)
                    steps.insert(0, '0')
                    self.matchers['0'] = self.matchers.pop('default')
                except ValueError:
                    steps.insert(0, 'default')
            else:
                try:
                    steps.sort(key=int)
                except ValueError:
                    pass  # already sorted alpha

        self.clear_state()
        self.state['steps'] = steps
        logger.debug(u'Passes: {}'.format(steps).encode('utf-8'))

    def bake(self, element, last_step=None):
        """Apply recipes to HTML tree. Will build recipes if needed."""

        if last_step is not None:
            try:
                self.state['steps'] = [s for s in self.state['steps']
                                       if int(s) < int(last_step)]
            except ValueError:
                self.state['steps'] = [s for s in self.state['steps']
                                       if s < last_step]
        for step in self.state['steps']:
            self.state['current_step'] = step
            self.state['scope'].insert(0, step)
            # Need to wrap each loop, since tree may have changed
            wrapped_html_tree = ElementWrapper.from_html_root(element)

            if not self.state[step]['recipe']:
                recipe = self.build_recipe(wrapped_html_tree, step)
            else:
                recipe = self.state[step]

            logger.debug(u'Recipe {} length: {}'.format(
                step, len(recipe['actions'])).encode('utf-8'))
            target = None
            old_content = {}
            node_counts = {}

            def process_actions(actions):
                global target, old_content

                for action, value in actions:
                    if action == 'target':
                        target = value
                        old_content = {}
                    elif action == 'tag':
                        target.tree.tag = str(value)
                    elif action == 'clear':
                        old_content['text'] = target.tree.text
                        target.tree.text = None
                        old_content['children'] = []
                        for child in target.tree:
                            old_content['children'].append(child)
                            target.tree.remove(child)
                    elif action == 'content':
                        if value is not None and value is not target.tree:
                            append_string(target, value.text)
                            for child in value:
                                target.tree.append(child)
                        elif old_content:
                            append_string(target, old_content['text'])
                            for child in old_content['children']:
                                target.tree.append(child)
                    elif action == 'attrib':
                        attname, vals = value
                        strval = self.resolve_value(vals)
                        target.tree.set(attname, strval)
                    elif action == 'string':
                        strval = self.resolve_value(value)
                        if target.location == 'before':
                            prepend_string(target, strval)
                        else:
                            append_string(target, strval)
                    elif action == 'move':
                        grouped_insert(target, value)
                    elif action == 'copy':
                        mycopy = util.copy_w_id_suffix(value)
                        mycopy.tail = None
                        grouped_insert(target, mycopy)
                    elif action == 'nodeset':
                        node_counts[value] = node_counts.setdefault(value, 0) + 1
                        suffix = u'_copy_{}'.format(node_counts[value])
                        mycopy = util.copy_w_id_suffix(value, suffix)
                        mycopy.tail = None
                        grouped_insert(target, mycopy)
                    elif action == 'drop':
                        parent = value.getparent()
                        if parent is not None:
                            parent.remove(value)
                    elif action == 'delayed':
                        process_actions(self.resolve_value(value))
                    else:
                        logger.warning(u'Missing action {}'.format(
                            action).encode('utf-8'))

            process_actions(recipe['actions'])

        # Do numbering

        # Do label/link updates

        # Add an empty string to each element just to make sure the element
        # is closed. This is useful for browsers that parse the output
        # as HTML5 rather than as XHTML5.
        #
        # One use-case would be users that inject the content into an
        # existing HTML (not XHTML) document.
        walkAll = element.iter()
        for elt in walkAll:
            if elt.tag not in SELF_CLOSING_TAGS:
                if len(elt) == 0 and not elt.text:
                    elt.text = ''

    def record_coverage_zero(self, rule, offset):
        """Add entry to coverage saying this selector was parsed"""
        self.coverage_lines.append('DA:{},0'.format(rule.source_line + offset))

    def record_coverage(self, rule):
        """Add entry to coverage saying this selector was matched"""
        logger.debug(u'Rule ({}): {}'.format(*rule).encode('utf-8'))
        self.coverage_lines.append('DA:{},1'.format(rule[0]))

    def record_coverage_line(self, line):
        """Add entry to coverage for declarations that were matched"""
        self.coverage_lines.append('DA:{},1'.format(line))

    def get_coverage_report(self):
        """Return the the bulk of the coverage report (selectors matched)"""
        return '\n'.join(self.coverage_lines)

    def build_recipe(self, element, step, depth=0):
        """Construct a set of steps to collate (and number) an HTML doc.

        Returns a state object that contains the steps to apply to the HTML
        tree. CSS rules match during a recusive descent HTML tree walk. Each
        declaration has a method that then runs, given the current element, the
        decaration value. State is maintained on the collator instance.  Since
        matching occurs when entering a node, declaration methods are ran
        either before or after recursing into its children, depending on the
        presence of a pseudo-element and its value.
        """
        element_id = element.etree_element.get('id')

        self.state['lang'] = element.lang

        matching_rules = {}
        #  specificity, order, pseudo, payload = match
        #  selector_rule, declaration_list, label = payload
        for _, _, pseudo, payload in self.matchers[step].match(element):
            rule, decs, label = payload
            matching_rules.setdefault(label, []).append((rule, decs))

        # Do non-pseudo
        if None in matching_rules:
            for rule, declarations in matching_rules.get(None):
                self.record_coverage(rule)
                self.push_target_elem(element)
                for decl in declarations:
                    self.run_method(element, decl, None)

        # Store all variables (strings and counters) before children
        if element_id:
            temp_counters = {}
            temp_strings = {}
            for s_step in self.state['scope']:
                temp_counters[s_step] = {
                        'counters': deepcopy(self.state[s_step]['counters'])}
                temp_strings[s_step] = {
                        'strings': deepcopy(self.state[s_step]['strings'])}

            self.state['counters'][element_id] = temp_counters
            self.state['strings'][element_id] = temp_strings

        # Do before
        if 'before' in matching_rules:
            for rule, declarations in matching_rules.get('before'):
                self.record_coverage(rule)
                # pseudo element, create wrapper
                self.push_pending_elem(element, 'before')
                for decl in declarations:
                    self.run_method(element, decl, 'before')
                # deal w/ pending_elements, per rule
                self.pop_pending_if_empty(element)

        # Recurse
        for el in element.iter_children():
            _state = self.build_recipe(el, step, depth=depth+1)  # noqa

        # Do after
        if 'after' in matching_rules:
            for rule, declarations in matching_rules.get('after'):
                self.record_coverage(rule)
                # pseudo element, create wrapper
                self.push_pending_elem(element, 'after')
                for decl in declarations:
                    self.run_method(element, decl, 'after')
                # deal w/ pending_elements, per rule
                self.pop_pending_if_empty(element)

        # Do outside
        if 'outside' in matching_rules:
            for rule, declarations in matching_rules.get('outside'):
                self.record_coverage(rule)
                self.push_pending_elem(element, 'outside')
                for decl in declarations:
                    self.run_method(element, decl, 'outside')

        # Do inside
        if 'inside' in matching_rules:
            for rule, declarations in matching_rules.get('inside'):
                self.record_coverage(rule)
                self.push_pending_elem(element, 'inside')
                for decl in declarations:
                    self.run_method(element, decl, 'inside')

        # Do deferred
        if ('deferred' in matching_rules or
             'after_deferred' in matching_rules or  # NOQA
             'before_deferred' in matching_rules or
             'outside_deferred' in matching_rules or
             'inside_deferred' in matching_rules):

            # store strings and counters, in case a deferred rule changes one
            if element_id:
                temp_counters = {}
                temp_strings = {}
                for s_step in self.state['scope']:
                    temp_counters[s_step] = {
                        'counters': deepcopy(self.state[s_step]['counters'])}
                    temp_strings[s_step] = {
                        'strings': deepcopy(self.state[s_step]['strings'])}

            # Do straight up deferred
            if 'deferred' in matching_rules:
                for rule, declarations in matching_rules.get('deferred'):
                    self.record_coverage(rule)
                    self.push_target_elem(element)
                    for decl in declarations:
                        self.run_method(element, decl, None)

            # Do before_deferred
            if 'before_deferred' in matching_rules:
                for rule, declarations in \
                        matching_rules.get('before_deferred'):
                    self.record_coverage(rule)
                    # pseudo element, create wrapper
                    self.push_pending_elem(element, 'before')
                    for decl in declarations:
                        self.run_method(element, decl, 'before')
                    # deal w/ pending_elements, per rule
                    self.pop_pending_if_empty(element)

            # Do after_deferred
            if 'after_deferred' in matching_rules:
                for rule, declarations in matching_rules.get('after_deferred'):
                    self.record_coverage(rule)
                    # pseudo element, create wrapper
                    self.push_pending_elem(element, 'after')
                    for decl in declarations:
                        self.run_method(element, decl, 'after')
                    # deal w/ pending_elements, per rule
                    self.pop_pending_if_empty(element)

            # Do outside_deferred
            if 'outside_deferred' in matching_rules:
                for rule, declarations in \
                        matching_rules.get('outside_deferred'):
                    self.record_coverage(rule)
                    self.push_pending_elem(element, 'outside')
                    for decl in declarations:
                        self.run_method(element, decl, 'outside')

            # Do inside_deferred
            if 'inside_deferred' in matching_rules:
                for rule, declarations in \
                        matching_rules.get('inside_deferred'):
                    self.record_coverage(rule)
                    self.push_pending_elem(element, 'inside')
                    for decl in declarations:
                        self.run_method(element, decl, 'inside')

            # Did a deferred rule change a stored variable?
            if element_id:
                for s_step in self.state['scope']:
                    for counter, val in self.state[s_step]['counters'].items():
                        if (counter not in temp_counters or
                                temp_counters[counter] != val):
                            self.state['counters'][element_id][s_step]['counters'][counter] = val  # NOQA
                    for string, val in self.state[s_step]['strings'].items():
                        if (string not in temp_strings or
                                temp_strings[string] != val):
                            self.state['strings'][element_id][s_step]['strings'][string] = val  # NOQA

        if 'target_id' in self.state[step]:
            del self.state[step]['target_id']

        if depth == 0:
            self.state[step]['recipe'] = True  # FIXME should ref HTML tree
        return self.state[step]

    def run_method(self, element, decl, pseudo):
        method = self.find_method(decl)
        try:
            method(element, decl, pseudo)
        except css.ParseError as ex:
            logger.warning(unicode(ex).encode('utf-8'))

    # Need target incase any declarations impact it

    def push_target_elem(self, element, pseudo=None):
        """Place target element onto action stack."""
        actions = self.state[self.state['current_step']]['actions']
        if len(actions) > 0 and actions[-1][0] == 'target':
            actions.pop()
        actions.append(('target', Target(element.etree_element,
                                         pseudo, element.parent.etree_element
                                         )))
        self.state[self.state['current_step']]['target_id'] = element.id

    def push_pending_elem(self, element, pseudo):
        """Create and place pending target element onto stack."""
        self.push_target_elem(element, pseudo)
        elem = etree.Element('div')
        actions = self.state[self.state['current_step']]['actions']
        actions.append(('move', elem))
        actions.append(('target', Target(elem)))

    def pop_pending_if_empty(self, element):
        """Remove empty wrapper element."""
        actions = self.state[self.state['current_step']]['actions']
        elem = self.current_target().tree
        if actions[-1][0] == ('target') and actions[-1][1].tree == elem:
            actions.pop()
            actions.pop()
            actions.pop()

    def current_target(self):
        """Return current target."""
        actions = self.state[self.state['current_step']]['actions']
        for action, value in reversed(actions):
            if action == 'target':
                return value

    # Declaration methods and accessor
    def find_method(self, decl):
        """Find class method to call for declaration based on name."""
        name = decl.name
        method = None
        try:
            method = getattr(self, u'do_{}'.format(
                             (name).replace('-', '_')))
        except AttributeError:
            if name.startswith('data-'):
                method = getattr(self, 'do_data_any')
            elif name.startswith('attr-'):
                method = getattr(self, 'do_attr_any')
            else:
                logger.warning(u'Missing method {}'.format(
                                 (name).replace('-', '_')).encode('utf-8'))
        if method:
            self.record_coverage_line(decl.source_line)
            return method
        else:
            return lambda x, y, z: None

    def lookup(self, vtype, vname, target_id=None):
        """Return value of vname from the variable store vtype.

        Valid vtypes are `strings` 'counters', and `pending`. If the value
        is not found in the current steps store, earlier steps will be
        checked. If not found, '', 0, or (None, None) is returned.
        """
        nullvals = {'strings': '', 'counters': 0, 'pending': (None, None)}
        nullval = nullvals[vtype]
        vstyle = None

        if vtype == 'counters':
            if len(vname) > 1:
                vname, vstyle = vname
            else:
                vname = vname[0]

        current_step = self.state['current_step']
        current_target = self.state[current_step].get('target_id')
        if target_id is not None and target_id != current_target:
            try:
                state = self.state[vtype][target_id]
                steps = self.state[vtype][target_id].keys()
            except KeyError:
                logger.warning(u'Bad ID target lookup {}'.format(
                    target_id).encode('utf-8'))
                return nullval

        else:
            state = self.state
            steps = self.state['scope']

        for step in steps:
            if vname in state[step][vtype]:
                if vtype == 'pending':
                    return(state[step][vtype][vname], step)
                else:
                    val = state[step][vtype][vname]
                    if vstyle is not None:
                        return self.counter_style(val, vstyle)
                    return val
        else:
            return nullval

    def counter_style(self, val, style):
        """Return counter value in given style."""
        if style == 'decimal-leading-zero':
            if val < 10:
                valstr = "0{}".format(val)
            else:
                valstr = str(val)
        elif style == 'lower-roman':
            valstr = _to_roman(val).lower()
        elif style == 'upper-roman':
            valstr = _to_roman(val)
        elif style == 'lower-latin' or style == 'lower-alpha':
            if 1 <= val <= 26:
                valstr = chr(val + 96)
            else:
                logger.warning('Counter out of range'
                               ' for latin (must be 1...26)')
                valstr = str(val)
        elif style == 'upper-latin' or style == 'upper-alpha':
            if 1 <= val <= 26:
                valstr = chr(val + 64)
            else:
                logger.warning('Counter out of range'
                               ' for latin (must be 1...26)')
                valstr = str(val)
        elif style == 'decimal':
            valstr = str(val)
        else:
            logger.warning(u"ERROR: Counter numbering not supported for"
                           u" list type {}. Using decimal.".format(
                               style).encode('utf-8'))
            valstr = str(val)
        return valstr

    def evaluate(self, element, value, type):
        """Evaluate an expression"""
        try:
            return expr.evaluate(self, element, value, type)
        except css.ParseError as ex:
            logger.warning(u"invalid syntax at {}".format(ex).encode('utf-8'))
            return type.default()

    def resolve_value(self, value):
        if isinstance(value, css.Value):
            return value.into_python(self)
        if isinstance(value, css.Delayed):
            return value.resolve(self)
        return value

    @log_decl_method
    def do_string_set(self, element, decl, pseudo):
        """Implement string-set declaration."""
        p = css.Parser(self, decl.value)

        for sub in p.separated('literal', ','):
            try:
                strname = sub.ident()
            except css.ParseError as ex:
                logger.warning(u"Bad string-set: {}"
                               .format(ex).encode('utf-8'))
                return

            strval = self.evaluate(element, sub.remaining(), css.String())
            step = self.state[self.state['current_step']]
            step['strings'][strname] = strval

    @log_decl_method
    def do_counter_reset(self, element, decl, pseudo):
        """Clear specified counters."""
        step = self.state[self.state['current_step']]
        p = css.Parser(self, decl.value)

        if p.eat('ident', 'none'):
            p.ensure_eos()
            return

        while not p.is_done:
            name = p.ident()
            value = p.try_(css.Parser.number, default=0)
            step['counters'][name] = value

            if p.eat('literal', ','):
                logger.warning(
                    u"Using comma in counter-reset is not standard CSS")

    @log_decl_method
    def do_counter_increment(self, element, decl, pseudo):
        """Increment specified counters."""
        step = self.state[self.state['current_step']]
        p = css.Parser(self, decl.value)

        if p.eat('ident', 'none'):
            p.ensure_eos()
            return

        while not p.is_done:
            name = p.ident()
            value = p.try_(css.Parser.number, default=1)

            if name in step['counters']:
                step['counters'][name] += value
            else:
                step['counters'][name] = value

            if p.eat('literal', ','):
                logger.warning(
                    u"Using comma in counter-increment is not standard CSS")

    @log_decl_method
    def do_node_set(self, element, decl, pseudo):
        """Implement node-set declaration."""
        p = css.Parser(self, decl.value)
        target = p.ident()
        p.ensure_eos()
        step = self.state[self.state['current_step']]
        elem = self.current_target().tree
        _, valstep = self.lookup('pending', target)
        if not valstep:
            step['pending'][target] = [('nodeset', elem)]
        else:
            self.state[valstep]['pending'][target] = [('nodeset', elem)]

    @log_decl_method
    def do_copy_to(self, element, decl, pseudo):
        """Implement copy-to declaration."""
        p = css.Parser(self, decl.value)
        target = p.ident()
        p.ensure_eos()
        step = self.state[self.state['current_step']]
        elem = self.current_target().tree
        _, valstep = self.lookup('pending', target)
        if not valstep:
            step['pending'][target] = [('copy', elem)]
        else:
            self.state[valstep]['pending'][target].append(('copy', elem))

    @log_decl_method
    def do_move_to(self, element, decl, pseudo):
        """Implement move-to declaration."""
        p = css.Parser(self, decl.value)
        target = p.ident()
        p.ensure_eos()
        step = self.state[self.state['current_step']]
        elem = self.current_target().tree

        #  Find if the current node already has a move, and remove it.
        actions = step['actions']
        for pos, action in enumerate(reversed(actions)):
            if action[0] == 'move' and action[1] == elem:
                target_index = - pos - 1
                actions[target_index:] = actions[target_index+1:]
                break

        _, valstep = self.lookup('pending', target)
        if not valstep:
            step['pending'][target] = [('move', elem)]
        else:
            self.state[valstep]['pending'][target].append(('move', elem))

    @log_decl_method
    def do_container(self, element, decl, pseudo):
        """Implement setting tag for new wrapper element."""
        p = css.Parser(self, decl.value)
        value = p.qname()
        p.ensure_eos()
        step = self.state[self.state['current_step']]
        actions = step['actions']
        actions.append(('tag', value))

    @log_decl_method
    def do_class(self, element, decl, pseudo):
        """Implement class declaration - pre-match."""
        step = self.state[self.state['current_step']]
        actions = step['actions']
        strval = self.evaluate(element, decl.value, css.String())
        actions.append(('attrib', ('class', strval)))

    @log_decl_method
    def do_attr_any(self, element, decl, pseudo):
        """Implement generic attribute setting."""
        step = self.state[self.state['current_step']]
        actions = step['actions']
        strval = self.evaluate(element, decl.value, css.String())
        actions.append(('attrib', (decl.name[5:], strval)))

    @log_decl_method
    def do_data_any(self, element, decl, pseudo):
        """Implement generic data attribute setting."""
        step = self.state[self.state['current_step']]
        actions = step['actions']
        strval = self.evaluate(element, decl.value, css.String())
        actions.append(('attrib', (decl.name, strval)))

    @log_decl_method
    def do_content(self, element, decl, pseudo):
        """Implement content declaration."""
        # FIXME Need?: link(id)
        step = self.state[self.state['current_step']]
        actions = step['actions']

        elem = self.current_target().tree
        if elem == element.etree_element or pseudo == 'inside':
            actions.append(('clear', elem))

        needs_copy = pseudo in ('before', 'after')
        action = 'move' if pseudo == 'outside' else 'content'
        include_nodes = (pseudo is not None) or None
        type = css.DocumentFragment(needs_copy, action, include_nodes)
        value = self.evaluate(element, decl.value, type).into_python(self)
        actions.extend(value)

        if pseudo and len(filter(lambda x: x[0] != 'drop', value)) == 0:
            actions.append(('drop', elem))

    @log_decl_method
    def do_group_by(self, element, decl, pseudo):
        """Implement group-by declaration - pre-match."""
        sort_css = groupby_css = flags = ''

        p = css.Parser(self, decl.value)
        args = map(lambda x: serialize(x.remaining()),
                   p.separated('literal', ',', 3))
        p.ensure_eos()

        if len(args) == 1:
            sort_css, = args
        elif len(args) == 2:
            sort_css, groupby_css = args
        else:
            sort_css, groupby_css, flags = args

        if groupby_css.strip() == 'nocase':
            flags = groupby_css
            groupby_css = ''
        sort = css_to_func(sort_css, flags,
                           self.css_namespaces, self.state['lang'])
        groupby = css_to_func(groupby_css, flags,
                              self.css_namespaces, self.state['lang'])
        step = self.state[self.state['current_step']]

        target = self.current_target()
        target.sort = sort
        target.lang = self.state['lang']
        target.isgroup = True
        target.groupby = groupby
        #  Find current target, set its sort/grouping as well
        for pos, action in \
                enumerate(reversed(step['actions'])):
            if action[0] == 'target' and \
                    action[1].tree == element.etree_element:
                action[1].sort = sort
                action[1].isgroup = True
                action[1].groupby = groupby
                break

    @log_decl_method
    def do_sort_by(self, element, decl, pseudo):
        """Implement sort-by declaration - pre-match."""
        if ',' in decl.value:
            css, flags = split(decl.value, ',')
        else:
            css = decl.value
            flags = None
        sort = css_to_func(serialize(css), serialize(flags or ''),
                           self.css_namespaces, self.state['lang'])
        step = self.state[self.state['current_step']]

        target = self.current_target()
        target.sort = sort
        target.lang = self.state['lang']
        target.isgroup = False
        target.groupby = None
        #  Find current target, set its sort as well
        for pos, action in \
                enumerate(reversed(step['actions'])):
            if action[0] == 'target' and \
                    action[1].tree == element.etree_element:
                action[1].sort = sort
                action[1].isgroup = False
                action[1].groupby = None
                break

    @log_decl_method
    def do_pass(self, element, decl, pseudo):
        """No longer valid way to set processing pass."""
        logger.warning(u"Old-style pass as declaration not allowed."
                       u"{}".format(decl.value).encpde('utf-8'))


def _itersplit(li, splitters):
    current = []
    for item in li:
        if item in splitters:
            yield current
            current = []
        else:
            current.append(item)
    yield current


def split(li, *splitters):
    """Split a list."""
    return [subl for subl in _itersplit(li, splitters) if subl]


def css_to_func(css, flags, css_namespaces, lang):
    """Convert a css selector to an xpath, supporting pseudo elements."""
    from cssselect import parse, HTMLTranslator
    from cssselect.parser import FunctionalPseudoElement
    #  FIXME HACK need lessc to support functional-pseudo-selectors instead
    #  of marking as strings and stripping " here.
    if not (css):
        return None

    sel = parse(css.strip('" '))[0]
    xpath = HTMLTranslator().selector_to_xpath(sel)

    first_letter = False
    if sel.pseudo_element is not None:
        if type(sel.pseudo_element) == FunctionalPseudoElement:
            if sel.pseudo_element.name in ('attr', 'first-letter'):
                xpath += '/@' + sel.pseudo_element.arguments[0].value
                if sel.pseudo_element.name == 'first-letter':
                    first_letter = True
        elif type(sel.pseudo_element) == unicode:
            if sel.pseudo_element == 'first-letter':
                first_letter = True

    xp = etree.XPath(xpath, namespaces=css_namespaces)

    def toupper(u):
        """Use icu library for locale sensitive uppercasing (python2)."""
        loc = Locale(lang) if lang else Locale()
        return unicode(UnicodeString(u).toUpper(loc))

    def func(elem):
        res = xp(elem)
        if res:
            if etree.iselement(res[0]):
                res_str = etree.tostring(res[0], encoding='unicode',
                                         method="text")
            else:
                res_str = res[0]
            if first_letter:
                if res_str:
                    if flags and 'nocase' in flags:
                        return toupper(res_str[0])
                    else:
                        return res_str[0]
                else:
                    return res_str
            else:
                if flags and 'nocase' in flags:
                    return toupper(res_str)
                else:
                    return res_str

    return func


def append_string(t, string):
    """Append a string to a node, as text or tail of last child."""
    node = t.tree
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


def prepend_string(t, string):
    """Prepend a string to a target node as text."""
    node = t.tree
    if node.text is not None:
        node.text += string
    else:
        node.text = string


def grouped_insert(t, value):
    """Insert value into the target tree 't' with correct grouping."""
    collator = Collator.createInstance(Locale(t.lang) if t.lang else Locale())
    if value.tail is not None:
        val_prev = value.getprevious()
        if val_prev is not None:
            val_prev.tail = (val_prev.tail or '') + value.tail
        else:
            val_parent = value.getparent()
            if val_parent is not None:
                val_parent.text = (val_parent.text or '') + value.tail
        value.tail = None
    if t.isgroup and t.sort(value) is not None:
        if t.groupby:
            for child in t.tree:
                if child.get('class') == 'group-by':
                    # child[0] is the label span
                    order = collator.compare(
                        t.groupby(child[1]) or '', t.groupby(value) or '')
                    if order == 0:
                        c_target = Target(child, sort=t.sort, lang=t.lang)
                        insert_group(value, c_target)
                        break
                    elif order > 0:
                        group = create_group(t.groupby(value))
                        group.append(value)
                        child.addprevious(group)
                        break
            else:
                group = create_group(t.groupby(value))
                group.append(value)
                t.tree.append(group)
        else:
            insert_group(value, t)

    elif t.sort and t.sort(value) is not None:
        insert_sort(value, t)

    elif t.location == 'inside':
        for child in t.tree:
            value.append(child)
        value.text = t.tree.text
        t.tree.text = None
        t.tree.append(value)

    elif t.location == 'outside':
        value.tail = t.tree.tail
        t.tree.tail = None
        parent = [n.getparent() for n in t.parent.iterdescendants()
                  if n == t.tree][0]
        parent.insert(parent.index(t.tree), value)
        value.append(t.tree)

    elif t.location == 'before':
        value.tail = t.tree.text
        t.tree.text = None
        t.tree.insert(0, value)
    else:
        t.tree.append(value)


def insert_sort(node, target):
    """Insert node into sorted position in target tree.

    Uses sort function and language from target"""
    sort = target.sort
    lang = target.lang
    collator = Collator.createInstance(Locale(lang) if lang else Locale())
    for child in target.tree:
        if collator.compare(sort(child) or '', sort(node) or '') > 0:
            child.addprevious(node)
            break
    else:
        target.tree.append(node)


def insert_group(node, target):
    """Insert node into in target tree, in appropriate group.

    Uses group and lang from target function.  This assumes the node and
    target share a structure of a first child that determines the grouping,
    and a second child that will be accumulated in the group.
    """
    group = target.sort
    lang = target.lang

    collator = Collator.createInstance(Locale(lang) if lang else Locale())
    for child in target.tree:
        order = collator.compare(group(child) or '', group(node) or '')
        if order == 0:
            for nodechild in node[1:]:
                child.append(nodechild)
            break
        elif order > 0:
            child.addprevious(node)
            break
    else:
        target.tree.append(node)


def create_group(value):
    """Create the group wrapper node."""
    node = etree.Element('div', attrib={'class': 'group-by'})
    span = etree.Element('span', attrib={'class': 'group-label'})
    span.text = value
    node.append(span)
    return node


def _extract_sel_info(sel):
    """Recurse down parsed tree, return pseudo class info"""
    from cssselect2.parser import (CombinedSelector, CompoundSelector,
                                   PseudoClassSelector,
                                   FunctionalPseudoClassSelector)
    steps = []
    extras = []
    if isinstance(sel, CombinedSelector):
        lstep, lextras = _extract_sel_info(sel.left)
        rstep, rextras = _extract_sel_info(sel.right)
        steps = lstep + rstep
        extras = lextras + rextras
    elif isinstance(sel, CompoundSelector):
        for ssel in sel.simple_selectors:
            s, e = _extract_sel_info(ssel)
            steps.extend(s)
            extras.extend(e)
    elif isinstance(sel, FunctionalPseudoClassSelector):
        if sel.name == 'pass':
            steps.append(serialize(sel.arguments).strip('"\''))
    elif isinstance(sel, PseudoClassSelector):
        if sel.name == 'deferred':
            extras.append('deferred')
    return (steps, extras)


def extract_selector_info(sel):
    """Return selector special pseudo class info (steps and other)."""
    #  walk the parsed_tree, looking for pseudoClass selectors, check names
    # add in steps and/or deferred extras
    steps, extras = _extract_sel_info(sel.parsed_tree)
    steps = sorted(set(steps))
    extras = sorted(set(extras))
    if len(steps) == 0:
        steps = ['default']
    return (steps, extras)


# convert integer to Roman numeral.
# From http://www.diveintopython.net/unit_testing/romantest.html
def _to_roman(num):
    """Convert integer to roman numerals."""
    roman_numeral_map = (
        ('M',  1000),
        ('CM', 900),
        ('D',  500),
        ('CD', 400),
        ('C',  100),
        ('XC', 90),
        ('L',  50),
        ('XL', 40),
        ('X',  10),
        ('IX', 9),
        ('V',  5),
        ('IV', 4),
        ('I',  1)
    )
    if not (0 < num < 5000):
        logger.warning('Number out of range for roman (must be 1..4999)')
        return str(num)
    result = ''
    for numeral, integer in roman_numeral_map:
        while num >= integer:
            result += numeral
            num -= integer
    return result
