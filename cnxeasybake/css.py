import logging
from lxml import etree
from tinycss2 import ast


__all__ = (
    'ParseError',
    'Parser',
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
        return value


class Value(object):
    """A typed value"""

    def __init__(self, type, value):
        self.type = type  # type: Type
        self.value = value

    def __repr__(self):
        return '<{} value: {!r}>'.format(self.type.name, self.value)

    def into_python(self, oven):
        """Convert this typed CSS value into a native Python value"""
        return self.type.convert_into(oven, self.value)


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
