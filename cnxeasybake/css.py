import itertools
import logging
from lxml import etree
from tinycss2 import ast, serialize

from . import util


__all__ = (
    'Delayed',
    'DocumentFragment',
    'ParseError',
    'Parser',
    'String',
    'Target',
    'Type',
    'Value',
)


logger = logging.getLogger('cnx-easybake')


class Type(object):
    """A CSS value type"""

    name = NotImplemented
    """Name of this type. For types which have names in CSS this should
    correspond to that name, for types which don't this should a string that
    could conceivably be a CSS type name.
    """

    def default(self):
        """Get default value for this type"""
        raise NotImplementedError()

    def convert_from(self, value):
        """Convert a native Python value into a :class:`Value` of this type."""
        if isinstance(value, Value) and value.type == self:
            return value

        logger.warning(u"Bad value for type {}: {!r}"
                       .format(self.name, value)
                       .encode('utf-8'))
        return self.default()

    def convert_into(self, oven, value):
        """Convert a :class:`Value` of this type into a native Python value"""
        if isinstance(value, Delayed):
            return value.resolve(oven)
        return value

    def is_immediate(self, value):
        """Can this value be resolved immediately?

        If this function returns ``True`` for a value, then
        :fn:`Type.convert_into` must accept ``None`` as value of ``oven`` for
        that value.
        """
        return not isinstance(value, Delayed)


class String(Type):
    """A CSS string type"""

    name = "string"

    def __eq__(self, other):
        return type(other) is String

    def default(self):
        return Value(self, "")

    def convert_from(self, value):
        if isinstance(value, (str, unicode, int, long)):
            return Value(self, unicode(value))

        if etree.iselement(value):
            value = etree.tostring(value,
                                   encoding='unicode',
                                   method='text',
                                   with_tail=False)
            return Value(self, value)

        if isinstance(value, list):
            value = map(lambda v: self.convert_from(v).value, value)
            if all(isinstance(x, (str, unicode)) for x in value):
                value = ''.join(value)
            return Value(self, value)

        if isinstance(value, Delayed):
            return Value(self, value)

        return super(type(self), self).convert_from(value)

    def convert_into(self, oven, value):
        if isinstance(value, list):
            return ''.join(map(lambda v: self.convert_into(oven, v), value))

        return super(String, self).convert_into(oven, value)

    def is_immediate(self, value):
        return not isinstance(value, list) \
           and super(String, self).is_immediate(value)


class DocumentFragment(Type):
    name = "document fragment"

    def __init__(self, needs_copy, action, include_nodes):
        self.needs_copy = needs_copy
        """Do we need to run fragments through :fun:`copy_w_id_suffix`?"""

        self.action = action
        """Action to perform on nodes in fragment"""

        self.include_nodes = include_nodes
        """Whether or not nodes should be included in list of action"""

    def default(self):
        return Value(self, [])

    def convert_from(self, value):
        if isinstance(value, (unicode, str, int, long)):
            return Value(self, [('string', unicode(value))])

        if etree.iselement(value):
            if self.needs_copy:
                value = util.copy_w_id_suffix(value)
            return Value(self, [(self.action, self.include_nodes and value)])

        if isinstance(value, list):
            value = map(lambda x: self.convert_from(x).value, value)
            value = list(itertools.chain.from_iterable(value))
            return Value(self, value)

        if isinstance(value, Value):
            if isinstance(value.type, String):
                return Value(self, [('string', value)])

        if isinstance(value, Delayed):
            return Value(self, [('delayed', value)])

        return super(DocumentFragment, self).convert_from(value)


class Value(object):
    """A typed value"""

    def __init__(self, type, value):
        self.type = type  # type: Type
        self.value = value

    def __repr__(self):
        return '<{} value: {!r}>'.format(self.type.name, self.value)

    def chain(self, func):  # type: (Callable[[T], Value]) -> Value
        """If this value can be resolved immediately do so and map it with
        ``func``, otherwise chain it with ``func`` via :class:``DelayedChain``.
        """
        if self.type.is_immediate(self.value):
            return Value(self.type, func(self.into_python(None)))
        return Value(self.type, DelayedChain(self.type, self, func))

    def into_python(self, oven):
        """Convert this typed CSS value into a native Python value"""
        return self.type.convert_into(oven, self.value)


class Delayed(object):
    """Value whose evaluation must be delayed until the entire step has been
    processed.
    """

    def resolve(self, oven):
        """Resolve this delayed to a concrete value"""
        raise NotImplementedError()


class Target(Delayed):
    """Value of a function evaluated on a node other than the one using
    the value. Such evaluation must be delayed as the other node might not have
    been processed yet.
    """

    def __init__(self, type, function, vref, arguments):
        self.type = type
        self.function = function
        self.vref = vref
        self.arguments = arguments

    def __repr__(self):
        return '<Delayed {}({}) at {}>'.format(
            self.function.name[7:], serialize(self.arguments), self.vref)

    def resolve(self, oven):
        vref = self.vref.into_python(oven)

        if vref[0] != '#':
            logger.warning(u"Invalid target for {}: {} does not begin with #"
                           .format(self.function.name, vref).encode('utf-8'))
            vref = '#nonexistent'

        element = FakeElement(vref[1:])
        func = ast.FunctionBlock(
            self.function.source_line,
            self.function.source_column + 7,
            self.function.name[7:],
            self.arguments,
        )
        return oven.evaluate(element, [func], self.type).into_python(oven)


class FakeElement:
    def __init__(self, id):
        self.id = id


class DelayedChain(Delayed):
    """Chain of delayed values. This represents result of a computation which
    relies on a delayed value, and thus must be delayed until said value can
    be resolved.
    """

    def __init__(self, type, base, func):
        self.type = type  # type: Type
        self.base = base  # type: Value
        self.func = func  # type: Callable[[T], Value]

    def __repr__(self):
        return '<Delayed chain {!r} through {!r}>'.format(self.base, self.func)

    def resolve(self, oven):
        base = self.base.into_python(oven)
        return self.type.convert_from(self.func(base)).into_python(oven)


class ParseError(Exception):
    def __init__(self, token, message):  # type: (ast.Node, str) -> None
        self.line = token.source_line
        self.column = token.source_column
        message = "{}:{}: {}".format(self.line, self.column, message)
        super(ParseError, self).__init__(message)


class Parser:
    def __init__(self, oven, source):  # type: (Oven, List[ast.Node]) -> None
        self._oven = oven  # type: Oven
        self._source = source  # type: List[ast.Node]
        self._position = 0
        """Position in `self._source` of the next token to parse"""

    @property
    def cur(self):
        """Current token"""
        return self._source[self._position]

    @property
    def is_done(self):
        """Are we finished parsing"""
        return self._position >= len(self._source)

    def next(self):  # type: () -> ast.Node
        """Get next token and advance parser. Raise :class:`ParseError` when
        trying to advance past end of source.
        """
        self._position += 1
        if self._position > len(self._source):
            raise ParseError(
                self._source[-1], "Expected more tokens after this one")
        return self._source[self._position - 1]

    # Primary parsing functions

    def ident(self):  # type: () -> str
        """Parse a CSS identifier"""
        self.skip_space()
        tok = self.next()

        if isinstance(tok, ast.IdentToken):
            return tok.value

        raise ParseError(tok, "Expected identifier, got {}".format(tok.type))

    def qname(self):  # type: () -> etree.QName
        """Parse a Qualified Name"""
        name = self.ident()

        if self.eat('literal', '|'):
            try:
                ns = self._oven.css_namespaces[name]
            except KeyError:
                raise ParseError(self._source[self._position - 1],
                                 "Unknown namespace: {}".format(name))

            name = self.ident()

        else:
            ns = None

        return etree.QName(ns, name)

    def number(self, type=long):  # type: (Callable[[str], T]) -> T
        """Parse a CSS number"""
        self.skip_space()
        tok = self.next()

        if isinstance(tok, ast.NumberToken):
            return type(tok.value)

        raise ParseError(tok, "Expected number, got {}".format(tok.type))

    def remaining(self):  # type: () -> List[ast.Node]
        """Consume all remaining tokens and return them as a list"""
        pos = self._position
        self._position = len(self._source)
        return self._source[pos:]

    def ensure_eos(self):  # type: () -> None
        """Ensure that all tokens in this parser have been consumed"""
        if not self.is_done:
            raise ParseError(self.cur, "Expected end of stream")

    def separated(self, type, value, max_count=None):
        # type () -> Iterable[Parser]
        """Iterator yielding parsers limited to subsequences of source delimited
        by specified token.

        The iterator consumes only the tokens it yields as sub-parsers,
        including any following separators.
        """
        while not self.is_done:
            start = self._position

            while not self.eat(type, value) and not self.is_done:
                self.next()

            end = self._position - 1 if not self.is_done else len(self._source)

            yield Parser(self._oven, self._source[start:end])

            if max_count is not None:
                max_count -= 1

                if max_count <= 0:
                    break

    # Helper functions

    def skip_space(self):  # type: () -> None
        """Skip a sequence of white-space tokens"""
        while not self.is_done and self.cur.type == 'whitespace':
            self._position += 1

    def eat(self, type, value):  # type: (str, Any) -> bool
        """If the next token matches ``type`` and reference ``value`` consume
        it and return ``True``, otherwise return ``False`` and leave parser
        unchanged.
        """
        if not self.is_done and self.cur.type == type \
        and self.cur.value == value:
            self._position += 1
            return True
        return False

    def try_(self, parser, default):  # type: (Callable[[Parser], T], T) -> T
        """Try parsing using provided ``parser`` and return its result if
        successful. Catch any :class:``ParseError``s and rewind parser back
        to where it was before calling ``try_``, returning ``default``.
        No other exceptions are caught.
        """
        position = self._position
        try:
            return parser(self)
        except ParseError:
            self._position = position
            return default
