"""Evaluation of CSS functions and expressions"""
import logging
from tinycss2 import ast, serialize

from . import css


logger = logging.getLogger('cnx-easybake')


FUNCTIONS = {}  # type: Dict[str, Callable[[Oven, ast.FunctionBlock, css.Parser, etree._Element, css.Type], css.Value]]
"""Mapping from name to evaluator of all known CSS functions."""


def evaluate(
    oven,       # type: Oven
    element,    # type: etree._Element
    p,          # type: Union[css.Parser, List[ast.Node]]
    type,       # type: css.Type
):  # type: (...) -> css.Value
    """Evaluate a CSS expression"""

    if not isinstance(p, css.Parser):
        p = css.Parser(oven, p)

    value = []  # type: List[Any]

    while not p.is_done:
        token = p.next()

        if isinstance(token, ast.WhitespaceToken):
            pass

        elif isinstance(token, (ast.StringToken,
                                ast.IdentToken,
                                ast.LiteralToken)):
            value.append(token.value)

        elif isinstance(token, ast.HashToken):
            value.append('#')
            value.append(token.value)

        elif isinstance(token, ast.FunctionBlock):
            try:
                fun = FUNCTIONS[token.lower_name]
            except KeyError:
                logger.warning(
                    u"{}:{}: Bad expression: unknown function: {}. {}"
                    .format(token.source_line,
                            token.source_column,
                            token.name,
                            serialize([token]))
                    .encode('utf-8'))
            else:
                args = css.Parser(oven, token.arguments)
                val = fun(oven, token, args, element, type)
                value.append(val)

        else:
            logger.warning(u"{}:{}: Bad expression: unrecognised token: {}. {}"
                           .format(token.source_line,
                                   token.source_column,
                                   token.type,
                                   serialize([token]))
                           .encode('utf-8'))

    if not value:
        return type.default()
    if len(value) == 1:
        value = value[0]
    return type.convert_from(value)


def function(name):
    def wrap(func):
        FUNCTIONS[name] = func
        return func
    return wrap
