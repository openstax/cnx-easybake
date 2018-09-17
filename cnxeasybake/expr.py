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


# https://www.w3.org/TR/2018/WD-css-values-4-20180814/#attr-notation
@function('attr')
def eval_attr(oven, func, p, element, type):
    name = p.qname()

    if p.eat('literal', ','):
        default = p.remaining()
    else:
        default = None

    p.ensure_eos()

    value = element.etree_element.get(name)
    if value is None:
        if default is not None:
            value = evaluate(oven, element, default, type)
        else:
            value = type.default()
    return value


@function('string')
def eval_string(oven, func, p, element, type):
    name = p.ident()

    if p.eat('literal', ','):
        default = p.remaining()
    else:
        default = None

    p.ensure_eos()

    value = oven.lookup('strings', name, element.id)
    if not value:
        if default:
            value = evaluate(oven, element, css.Parser(oven, default), type)
        else:
            logger.warning(u"{} blank string".format(name).encode('utf-8'))
            value = type.default()

    return value
