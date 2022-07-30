import math, sys

deep_thought = 42

def sqrt(x):
    return math.sqrt(x)

def print_square(x):
    print(x*x)

def hello_world():
    sys.stdout.write('hello, world')

def factorial(n):
    res = 1
    for i in range(n):
        res *= i+1
    return res