import judge_util

RawCheck = judge_util.teststage(exercise_style=judge_util.ExerciseStyle.AS_IS)


@judge_util.check_method(RawCheck)
def question_exists(self):
    import string
    src = judge_util.extract_question_cell_source(self)
    punctuations = frozenset(string.punctuation)
    if ''.join(x for x in ''.join(src.split()) if x not in punctuations):
        # Non-whitespace and non-punctuation characters exist
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
        import traceback
        judge_util.set_unsuccessful_message(self, ''.join(traceback.format_exception(None, e, None)))
        self.fail()
    except NameError as e:
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
