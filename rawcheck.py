import judge_util

RawCheck = judge_util.teststage()
RawCheck.mode = 'separate'

@judge_util.check_method(RawCheck, 'TE')
def toplevel_check(self):
    try:
        def canary_open(*args, **kwargs):
            judge_util.set_fail_tag(self, 'IOT')
            self.fail()
        exec(self.submission, {'__name__': '__main__', 'open': canary_open})
    except SyntaxError as e:
        if '!' in e.text:
            judge_util.set_fail_tag(self, 'SCE')
        elif '%' in e.text:
            judge_util.set_fail_tag(self, 'MCE')
        else:
            judge_util.set_fail_tag(self, 'SE')
        import traceback
        judge_util.set_unsuccessful_message(self, ''.join(traceback.format_exception(None, e, None)))
        self.fail()
    except NameError as e:
        judge_util.set_fail_tag(self, 'UNU')
        import traceback
        judge_util.set_unsuccessful_message(self, ''.join(traceback.format_exception(None, e, None)))
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
    if flag_assignment_exists(self.submission, 'QUESTION_EXISTS'):
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
