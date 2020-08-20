#!/usr/bin/env python3

import ast, inspect
import unittest
import sys, io

class NullFunctionException(Exception):
    pass

class LoopFoundException(Exception):
    pass

class CongruenceException(Exception):
    pass

def raise_if_null_function(f, offset_indent=0):
    src = '\n'.join(x[offset_indent:] for x in inspect.getsource(f).splitlines())
    for node in ast.walk(ast.parse(src)):
        if type(node) == ast.FunctionDef \
           and node.name == f.__name__ \
           and len(node.body) == 1 \
           and type(node.body[0]) == ast.Expr:
            if type(node.body[0].value) == ast.Ellipsis: #NOTE: Deprecated in 3.8
                # Python <= 3.7
                raise NullFunctionException
            if type(node.body[0].value) == ast.Constant and node.body[0].value.value == ...:
                # Python >= 3.8
                raise NullFunctionException

def raise_if_loop_exists(f):
    source = inspect.getsource(f)
    node_types = {type(n) for n in ast.walk(ast.parse(source))}
    if ast.For in node_types:
        raise LoopFoundException('For loop found')
    if ast.While in node_types:
        raise LoopFoundException('While loop found')

def raise_if_congruent(f, g):
    name_map = {f.__name__:  g.__name__}
    def eq(x, y):
        if type(x) != type(y):
            return False
        if type(x) == ast.Constant:
            return x.value == y.value
        if type(x) == ast.Name:
            return x.id == y.id or name_map.get(x.id) == y.id
        return True
    def ast_nodes(h):
        return ast.walk(ast.parse(inspect.getsource(h)))
    if all(eq(n, m) or n == m for n, m in zip(ast_nodes(f), ast_nodes(g))):
        raise CongruenceException

class JudgeTestCase(unittest.TestCase):
    pass

def judge_case(kind, score):
    assert kind in 'CO'
    assert type(score) == int and score > 0

    def decorator(func):
        name = f'test_{kind}_{score}_0_{func.__name__}'
        method = staticmethod(func) if kind == 'C' else func
        setattr(JudgeTestCase, name, method)
        return func

    return decorator

def judge_precheck(score):
    return judge_case('C', score)

def judge_test(score):
    return judge_case('O', score)

def argument_logger(f):
    def argrepr(x):
        if isinstance(x, io.TextIOBase):
            pos = x.tell()
            s = x.read()
            x.seek(pos)
            return f'File({repr(s)})'
        else:
            return repr(x)
    def cutoff(s, limit=256):
        return s[:limit] + '...' if len(s) >= limit else s
    def wrapper(*args, **kwargs):
        args_repr = [cutoff(argrepr(x)) for x in args]
        args_repr.extend(f'{k}={cutoff(argrepr(v))}' for k, v in kwargs.items())
        print(f'Called: {f.__name__}({", ".join(args_repr)})', file=sys.stderr)
        return f(*args, **kwargs)
    return f if 'IPython' in sys.modules else wrapper
