#!/usr/bin/env -S testcase_translator.py -sa -cf

from testcase_util import *

deep_thought = [
    (None, 42),
]

sqrt = [
    ((4,), 2, approx()),
    ((2,), 1.41, approx(2)),
    ((2,), 1.41, approx(None,delta=0.005)),
]

print_square = [
    ((2,), printed(4)),
    ((2,), printed('4', sep=' ', end='')),
]

hello_world = [
    ((), stdout('hello, world')),
]

factorial = [
    ((2,), call_count(1), '>'),
    ((2,), recursively_called()),
]
