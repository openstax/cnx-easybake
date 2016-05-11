#!/usr/bin/env python
"""Implement a collator that moves content defined by CSS3 rules to HTML."""
import logging
from lxml import etree
import tinycss2
from tinycss2 import serialize, parse_declaration_list, ast
import cssselect2
from cssselect2 import ElementWrapper
from copy import deepcopy

verbose = False

logger = logging.getLogger('cnx-easybake')


class Target():
    """Represent the target for a move or copy."""

    def __init__(self, tree, location, sort, isgroup, groupby):
        """Set up target object."""
        self.tree = tree
        self.location = location
        self.sort = sort
        self.isgroup = isgroup
        self.groupby = groupby

    def __str__(self):
        """Return string."""
        return ("tree: {0.tree} "
                "location: {0.location} "
                "sort: {0.sort} "
                "isgroup: {0.isgroup} "
                "groupby: {0.groupby}".format(self))


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
            self.matchers = {}
            self.clear_state()

    def clear_state(self):
        """Clear the recipe state."""
        self.state = {}
        steps = sorted(self.matchers.keys())
        if len(steps) > 0:
            steps.remove('default')
            try:
                steps.sort(key=int)
            except ValueError:
                pass
            steps.insert(0, 'default')
        self.state['steps'] = steps
        self.state['current_step'] = None
        self.state['scope'] = []
        self.state['counters'] = {}
        for step in self.matchers:
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

        if clear_css:
            self.matchers = {}

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
                    steps, decls = parse_rule_steps(rule)
                    for sel in selectors:
                        pseudo = sel.pseudo_element
                        for step in steps:
                            if step not in self.matchers:
                                self.matchers[step] = cssselect2.Matcher()
                            self.matchers[step].add_selector(sel,
                                                             (decls, pseudo))

        # always clears state, since rules have changed
        self.clear_state()

    def bake(self, element):
        """Apply recipes to HTML tree. Will build recipes if needed."""
        for step in self.state['steps']:
            self.state['current_step'] = step
            self.state['scope'].insert(0, step)
            # Need to wrap each loop, since tree may have changed
            wrapped_html_tree = ElementWrapper.from_html_root(element)

            if not self.state[step]['recipe']:
                recipe = self.build_recipe(wrapped_html_tree, step)
            else:
                recipe = self.state[step]

            target = None
            old_content = {}
            for action, value in recipe['actions']:
                if action == 'target':
                    target = value
                    old_content = {}
                elif action == 'clear':
                    old_content['text'] = target.tree.text
                    target.tree.text = None
                    old_content['children'] = []
                    for child in target.tree:
                        old_content['children'].append(child)
                        target.tree.remove(child)
                elif action == 'content':
                    if value is not None:
                        append_string(target, value.text)
                        for child in value:
                            target.tree.append(child)
                    elif old_content:
                        append_string(target, old_content['text'])
                        for child in old_content['children']:
                            target.tree.append(child)
                elif action == 'attrib':
                    target.tree.set(*value)
                elif action == 'string':
                    if target.location == 'before':
                        prepend_string(target, value)
                    else:
                        append_string(target, value)
                elif action == 'target-counter':
                    el_id, cname = value
                    strval = str(self.lookup('counters', cname, el_id) or 0)
                    if target.location == 'before':
                        prepend_string(target, strval)
                    else:
                        append_string(target, strval)
                elif action == 'move':
                    grouped_insert(target, value)

                elif action == 'copy':
                    mycopy = deepcopy(value)  # FIXME deal w/ ID values
                    mycopy.tail = None
                    grouped_insert(target, mycopy)
                else:
                    logger.warning('Missing action {}'.format(action))

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
        presence of a pseudo-element and its value.
        """
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
                self.push_target_elem(element)
                for decl in declarations:
                    method = self.find_method(decl.name)
                    method(element, decl, None)
                self.pop_target_elem(element)

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

        element_id = element.etree_element.get('id')
        if element_id:
            self.state['counters'][element_id] = {}
            for step in self.state['scope']:
                self.state['counters'][element_id][step] = \
                        {'counters': deepcopy(self.state[step]['counters'])}

        if depth == 0:
            self.state[step]['recipe'] = True  # FIXME should ref HTML tree
        return self.state[step]

    # Need target incase any declarations impact it
    def push_target_elem(self, element):
        """Place target element onto action stack."""
        self.state[self.state['current_step']]['actions'].\
            append(('target', Target(element.etree_element,
                                     None, None, False, None)))

    def pop_target_elem(self, element):
        """Remove target element from stacki if not used."""
        actions = self.state[self.state['current_step']]['actions']
        if actions[-1][0] == 'target' and \
           actions[-1][1].tree == element.etree_element:
            actions.pop()

    # Maintain stack of pending wrapper elements
    def push_pending_elem(self, element):
        """Create and place pending target element onto stack."""
        elem = etree.Element('div')
        self.state[self.state['current_step']]['pending_elems'].\
            append((element, Target(elem, None, None, False, None)))

    def pop_pending_elem(self, element):
        """Remove pending target element from stack."""
        if self.is_pending_element(element):
            self.state[self.state['current_step']]['pending_elems'].pop()

    def is_pending_element(self, element):
        """Determine if most recent pending is for this element."""
        step = self.state[self.state['current_step']]
        return len(step['pending_elems']) > 0 \
            and step['pending_elems'][-1][0] == element

    # Declaration methods and accessor
    def find_method(self, name):
        """Find class method to call for declaration based on name."""
        method = None
        try:
            method = getattr(self, 'do_{}'.format(
                             (name).replace('-', '_')))
        except AttributeError:
            if name.startswith('data-'):
                method = getattr(self, 'do_data_any')
            elif name.startswith('attr-'):
                method = getattr(self, 'do_attr_any')
            else:
                logger.warning('Missing method {}'.format(
                                 (name).replace('-', '_')))
        if method:
            return method
        else:
            return lambda x, y, z: None

    def lookup(self, vtype, vname, target_id=None):
        """Return value of vname from the variable store vtype.

        Valid vtypes are `strings` `pending` and `counters`. If the value
        is not found in the current steps store, ealier steps will be
        checked. If not found None is returned
        """
        if target_id is not None:
            try:
                state = self.state[vtype][target_id]
                steps = self.state[vtype][target_id].keys()
            except KeyError:
                logger.warning('Bad ID target lookup {}'.format(target_id))
                return None

        else:
            state = self.state
            steps = self.state['scope']

        for step in steps:
            if vname in state[step][vtype]:
                if vtype == 'pending':
                    return(state[step][vtype][vname], step)
                else:
                    return state[step][vtype][vname]
        if vtype == 'pending':
            return (None, None)
        else:
            return None

    def eval_string_value(self, element, value):
        """Evaluate parsed string and return its value."""
        strval = ''
        args = serialize(value)

        for term in value:
            if type(term) is ast.WhitespaceToken:
                pass

            elif type(term) is ast.StringToken:
                strval += term.value

            elif type(term) is ast.IdentToken:
                logger.debug("IdentToken as string: {}".format(term.value))
                strval += term.value

            elif type(term) is ast.LiteralToken:
                logger.debug("LiteralToken as string: {}".format(term.value))
                strval += term.value

            elif type(term) is ast.FunctionBlock:
                if term.name == 'string':
                    strname = serialize(term.arguments)
                    val = self.lookup('strings', strname)
                    if val is None:
                        logger.warning("{} blank string".
                                       format(strname))
                        continue
                    strval += val

                elif term.name == u'attr':
                    att_name = serialize(term.arguments)
                    strval += element.etree_element.get(att_name, '')

                elif term.name == u'content':
                    strval += etree.tostring(element.etree_element,
                                             encoding='unicode',
                                             method='text')

                elif term.name == u'first-letter':
                    tmpstr = self.eval_string_value(element, term.arguments)
                    if tmpstr:
                        strval += tmpstr[0]

                elif term.name == u'pending':
                    logger.warning("Bad string value: pending() not allowed."
                                   "{}".format(args))
        return strval.strip()

    def do_string_set(self, element, decl, pseudo):
        """Implement string-set declaration."""
        args = serialize(decl.value)
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'string-set', args))
        step = self.state[self.state['current_step']]

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
                    val = self.lookup('strings', other_strname)
                    if val is None:
                        logger.warning("{} blank string".
                                       format(strname))
                        continue
                    if strname is not None:
                        strval += val
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == 'counter':
                    countername = serialize(term.arguments)
                    count = self.lookup('counters', countername) or 1
                    strval += str(count)

                elif term.name == u'attr':
                    if strname is not None:
                        att_name = serialize(term.arguments)
                        strval += element.etree_element.get(att_name, '')
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == u'content':
                    if strname is not None:
                        strval += etree.tostring(element.etree_element,
                                                 encoding='unicode',
                                                 method='text')
                    else:
                        logger.warning("Bad string-set: {}".format(args))

                elif term.name == u'first-letter':
                    tmpstr = self.eval_string_value(element, term.arguments)
                    if tmpstr:
                        strval += tmpstr[0]

                elif term.name == u'pending':
                    logger.warning("Bad string-set:pending() not allowed. {}".
                                   format(args))

        if strname is not None:
            step['strings'][strname] = strval

    def do_counter_reset(self, element, decl, pseudo):
        """Clear specified counters."""
        target = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'counter-reset', target))
        counter_name = ''
        for term in decl.value:
            if type(term) is ast.WhitespaceToken:
                continue

            elif type(term) is ast.IdentToken:
                if counter_name:
                    step['counters'][counter_name] = 0
                counter_name = term.value

            elif type(term) is ast.LiteralToken:
                if counter_name:
                    step['counters'][counter_name] = 0
                    counter_name = ''

            elif type(term) is ast.NumberToken:
                if counter_name:
                    step['counters'][counter_name] = int(term.value)
                    counter_name = ''

            else:
                logger.warning("Unrecognized counter-reset term {}".
                               format(type(term)))
        if counter_name:
            step['counters'][counter_name] = 0

    def do_counter_increment(self, element, decl, pseudo):
        """Increment specified counters."""
        target = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'counter-increment', target))
        counter_name = ''
        for term in decl.value:
            if type(term) is ast.WhitespaceToken:
                continue

            elif type(term) is ast.IdentToken:
                if counter_name:
                    if counter_name in step['counters']:
                        step['counters'][counter_name] += 1
                    else:
                        step['counters'][counter_name] = 1
                counter_name = term.value

            elif type(term) is ast.LiteralToken:
                if counter_name:
                    if counter_name in step['counters']:
                        step['counters'][counter_name] += 1
                    else:
                        step['counters'][counter_name] = 1
                    counter_name = ''

            elif type(term) is ast.NumberToken:
                if counter_name:
                    if counter_name in step['counters']:
                        step['counters'][counter_name] += int(term.value)
                    else:
                        step['counters'][counter_name] = int(term.value)
                    counter_name = ''

            else:
                logger.warning("Unrecognized counter-increment term {}".
                               format(type(term)))
        if counter_name:
            if counter_name in step['counters']:
                step['counters'][counter_name] += 1
            else:
                step['counters'][counter_name] = 1

    def do_node_set(self, element, decl, pseudo):
        """Implement node-set declaration."""
        target = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'node-set', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = step['pending_elems'][-1][1].tree
        _, valstep = self.lookup('pending', target)
        if not valstep:
            step['pending'][target] = [('copy', elem)]
        else:
            self.state[valstep]['pending'][target] = [('copy', elem)]

    def do_copy_to(self, element, decl, pseudo):
        """Implement copy-to declaration."""
        target = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'copy-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = step['pending_elems'][-1][1].tree
        _, valstep = self.lookup('pending', target)
        if not valstep:
            step['pending'][target] = [('copy', elem)]
        else:
            self.state[valstep]['pending'][target].append(('copy', elem))

    def do_move_to(self, element, decl, pseudo):
        """Implement move-to declaration."""
        target = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'move-to', target))
        if pseudo is None:
            elem = element.etree_element
        elif self.is_pending_element(element):
            elem = step['pending_elems'][-1][1].tree

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

    def do_container(self, element, decl, pseudo):
        """Implement setting tag for new wrapper element."""
        value = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'container', value))
        if self.is_pending_element(element):
            step['pending_elems'][-1][1].tree.tag = value

    def do_class(self, element, decl, pseudo):
        """Implement class declaration - pre-match."""
        value = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        actions = step['actions']
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'class', value))
        strval = self.eval_string_value(element, decl.value)
        if self.is_pending_element(element):
            step['pending_elems'][-1][1].tree.set('class', strval)
        else:
            actions.append(('attrib', ('class', strval)))

    def do_attr_any(self, element, decl, pseudo):
        """Implement generic attribute setting."""
        value = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        actions = step['actions']
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, decl.name, value))
        strval = self.eval_string_value(element, decl.value)
        if self.is_pending_element(element):
            step['pending_elems'][-1][1].tree.set(decl.name[5:], strval)
        else:
            actions.append(('attrib', (decl.name[5:], strval)))

    def do_data_any(self, element, decl, pseudo):
        """Implement generic data attribute setting."""
        value = serialize(decl.value).strip()
        step = self.state[self.state['current_step']]
        actions = step['actions']
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, decl.name, value))
        strval = self.eval_string_value(element, decl.value)
        if self.is_pending_element(element):
            step['pending_elems'][-1][1].tree.set(decl.name, strval)
        else:
            actions.append(('attrib', (decl.name, strval)))

    def do_content(self, element, decl, pseudo):
        """Implement content declaration."""
        # FIXME Need?: link(id)
        value = serialize(decl.value).strip()
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'content', value))

        step = self.state[self.state['current_step']]
        actions = step['actions']

        elem = pending_target = None
        wastebin = []
        if self.is_pending_element(element):
            pending_target = step['pending_elems'][-1][1]
            elem = pending_target.tree
        else:
            elem = element.etree_element

        actions.append(('target', Target(element.etree_element, pseudo,
                                         None, False, None)))
        if pending_target:
            actions.append(('move', pending_target.tree))
            actions.append(('target', pending_target))
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
                    val = self.lookup('strings', strname)
                    if val is None:
                        logger.warning("{} blank string".
                                       format(strname))
                        continue
                    actions.append(('string', val))

                elif term.name == 'counter':
                    countername = serialize(term.arguments)
                    count = self.lookup('counters', countername) or 0
                    actions.append(('string', str(count)))

                elif term.name == 'target-counter':
                    args = [serialize(a).strip('" \'')
                            for a in split(term.arguments, ',')]
                    actions.append(('target-counter', args))

                elif term.name == u'attr':
                    att_name = serialize(term.arguments)
                    actions.append(('string',
                                    element.etree_element.get(att_name, '')))

                elif term.name == u'first-letter':
                    tmpstr = self.eval_string_value(element, term.arguments)
                    if tmpstr:
                        actions.append(('string', tmpstr[0]))

                elif term.name == u'content':
                    if pseudo:
                        # FIXME deal w/ IDs
                        mycopy = deepcopy(element.etree_element)
                        actions.append(('content', mycopy))
                    else:
                        actions.append(('content', None))

                elif term.name == 'pending':
                    target = serialize(term.arguments)
                    val, val_step = self.lookup('pending', target)
                    if val is None:
                        logger.warning("{} empty bucket".format(target))
                        continue
                    actions.extend(val)
                    del self.state[val_step]['pending'][target]

                elif term.name == 'nodes':
                    target = serialize(term.arguments)
                    val, val_step = self.lookup('pending', target)
                    if val is None:
                        logger.warning("{} empty bucket".format(target))
                        continue
                    for action in val:
                            if action[0] == 'move':
                                actions.append(('copy', action[1]))
                            else:
                                actions.append(action)

                elif term.name == u'clear':
                    target = serialize(term.arguments)
                    val, val_step = self.lookup('pending', target)
                    if val is None:
                        logger.warning("{} empty bucket".format(target))
                        continue
                    wastebin.extend(val)
                    del self.state[val_step]['pending'][target]

                else:
                    logger.warning("Unknown function {}".format(term.name))
            else:
                logger.warning("Unknown term {}".
                               format(decl.value))

        if self.is_pending_element(element):
            if actions[-1][0] == ('target') \
                    and actions[-1][1].tree == elem:
                actions.pop()
                actions.pop()

        if len(wastebin) > 0:
            trashbucket = etree.Element('div',
                                        attrib={'class': 'delete-me'})
            actions.append(('target', Target(trashbucket, None,
                                             None, False, None)))
            actions.extend(wastebin)
            wastebin = []

    def do_group_by(self, element, decl, pseudo):
        """Implement group-by declaration - pre-match."""
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'group-by', serialize(decl.value)))
        sort_css = groupby_css = flags = ''
        if ',' in decl.value:
            if decl.value.count(',') == 2:
                sort_css, groupby_css, flags = \
                        map(serialize, split(decl.value, ','))
            else:
                sort_css, groupby_css = map(serialize, split(decl.value, ','))
        else:
            sort_css = serialize(decl.value)
        if groupby_css.strip() == 'nocase':
            flags = groupby_css
            groupby_css = ''
        sort = css_to_func(sort_css, flags)
        groupby = css_to_func(groupby_css, flags)
        step = self.state[self.state['current_step']]

        if self.is_pending_element(element):
            target = step['pending_elems'][-1][1]
            target.sort = sort
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

    def do_sort_by(self, element, decl, pseudo):
        """Implement sort-by declaration - pre-match."""
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'sort-by', serialize(decl.value)))

        if ',' in decl.value:
            css, flags = split(decl.value, ',')
        else:
            css = decl.value
            flags = None
        sort = css_to_func(serialize(css), serialize(flags or ''))
        step = self.state[self.state['current_step']]

        if self.is_pending_element(element):
            target = step['pending_elems'][-1][1]
            target.sort = sort
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

    def do_pass(self, element, decl, pseudo):
        """Set processing pass for this ruleset."""
        logger.debug("{} {} {} {}".format(self.state['current_step'],
                     element.local_name, 'pass', serialize(decl.value)))
        pass  # Handled in parse_rule_steps


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


def css_to_func(css, flags=None):
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

    xp = etree.XPath(xpath)

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
                        return res_str[0].upper()
                    else:
                        return res_str[0]
                else:
                    return res_str
            else:
                if flags and 'nocase' in flags:
                    return res_str.upper()
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
    if t.isgroup and t.sort(value) is not None:
        if t.groupby:
            for child in t.tree:
                if child.get('class') == 'group-by':
                    # child[0] is the label span
                    if t.groupby(child[1]) == t.groupby(value):
                        insert_group(value, child, t.sort)
                        break
                    elif t.groupby(child[1]) > t.groupby(value):
                        group = create_group(t.groupby(value))
                        group.append(value)
                        child.addprevious(group)
                        break
            else:
                group = create_group(t.groupby(value))
                group.append(value)
                t.tree.append(group)
        else:
            insert_group(value, t.tree, t.sort)

    elif t.sort and t.sort(value) is not None:
        insert_sort(value, t.tree, t.sort)
    elif t.location == 'before':
        value.tail = t.tree.text
        t.tree.text = None
        t.tree.insert(0, value)
    else:
        t.tree.append(value)


def insert_sort(node, target, sort):
    """Insert node into sorted position in target, using sort function."""
    for child in target:
        if sort(child) > sort(node):
            child.addprevious(node)
            break
    else:
        target.append(node)


def insert_group(node, target, group):
    """Insert node into in target, using group function.

    This assumes the node and target share a structure of a first child
    that determines the grouping, and a second child that will be accumulated
    in the group.
    """
    for child in target:
        if group(child) == group(node):
            for nodechild in node[1:]:
                child.append(nodechild)
            break
        elif group(child) > group(node):
            child.addprevious(node)
            break
    else:
        target.append(node)


def create_group(value):
    """Create the group wrapper node."""
    node = etree.Element('div', attrib={'class': 'group-by'})
    span = etree.Element('span', attrib={'class': 'group-label'})
    span.text = value
    node.append(span)
    return node


def parse_rule_steps(rule):
    """Return rule steps and declartions."""
    declarations = parse_declaration_list(rule.content, skip_whitespace=True)
    steps = []
    for decl in declarations:
        if decl.name == 'pass':
            strval = ''
            value = decl.value
            args = serialize(value)
            for term in value:
                if type(term) is ast.WhitespaceToken:
                    pass

                elif type(term) is ast.StringToken:
                    strval += term.value

                elif type(term) is ast.NumberToken:
                    strval += str(int(term.value))

                elif type(term) is ast.IdentToken:
                    logger.debug("IdentToken as string: {}".format(term.value))
                    strval += term.value

                elif type(term) is ast.LiteralToken:
                    steps.append(strval)
                    strval = ''

                elif type(term) is ast.FunctionBlock:
                        logger.warning("Bad pass name: functions not allowed."
                                       "{}".format(args))
            if strval != '':
                steps.append(strval)
    if len(steps) == 0:
        steps.append('default')

    return (steps, declarations)
