import judge_util

RawCheck = judge_util.teststage()
RawCheck.mode = 'separate'

@judge_util.check_method(RawCheck, 'TE')
def toplevel_check(self):
    with open(judge_util.SUBMISSION_FILENAME, encoding='utf-8') as f:
        src = f.read()
    try:
        def canary_open(*args, **kwargs):
            judge_util.set_fail_tag(self, 'IOT')
            self.fail()
        exec(src, {'__name__': '__main__', 'open': canary_open})
    except SyntaxError as e:
        if '!' in e.text:
            judge_util.set_fail_tag(self, 'SCE')
        elif '%' in e.text:
            judge_util.set_fail_tag(self, 'MCE')
        else:
            judge_util.set_fail_tag(self, 'SE')
        self.fail()
    except FileNotFoundError:
        judge_util.set_fail_tag(self, 'IOT')
        self.fail()
    except ModuleNotFoundError:
        judge_util.set_fail_tag(self, 'UMI')
        self.fail()
    except Exception:
        self.fail()

@judge_util.check_method(RawCheck)
def question_exists(self):
    with open(judge_util.SUBMISSION_FILENAME, encoding='utf-8') as f:
        src = f.read()
    if flag_assignment_exists(src, 'QUESTION_EXISTS'):
        judge_util.set_ok_tag(self, 'QE')

def flag_assignment_exists(src, var):
    try:
        env = {'__name__': '__main__'}
        exec(src, env)
    except SyntaxError as e:
        import re
        return re.search(rf'^\s*{var}\s*=\s*True', src, re.MULTILINE)
    except Exception:
        import ast
        return any(isinstance(node, ast.Assign)
               and len(node.targets) == 1
               and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == var
               and isinstance(node.value, ast.Constant)
               and node.value.value is True
               for node in ast.walk(ast.parse(src)))
    else:
        return env.get(var, False)
