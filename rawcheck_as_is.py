import judge_util

RawCheck = judge_util.teststage(exercise_style=judge_util.ExerciseStyle.AS_IS)


@judge_util.check_method(RawCheck)
def question_exists(self):
    src = judge_util.extract_question_cell_source(self)
    if src.strip():
        judge_util.set_ok_tag(self, 'QE')


@judge_util.check_method(RawCheck, 'TE')
def toplevel_check(self):
    src = judge_util.extract_answer_cell_source(self)
    if src == '':
        return
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
