import judge_util

CheckAsIs = judge_util.teststage(exercise_style=judge_util.ExerciseStyle.AS_IS)


@judge_util.check_method(CheckAsIs)
def code_cell_run(self):
    ipynb = self.submission
    exec_counts = [cell['execution_count'] for cell in ipynb['cells'] if cell['cell_type'] == 'code' and judge_util.cell_source_str(cell).strip()]
    if exec_counts:
        if all(x is not None for x in exec_counts):
            judge_util.set_ok_tag(self, judge_util.EvaluationTag('AR', 'All Run', '#97ff8a', '#006414'))
        if all(x is None for x in exec_counts):
            judge_util.set_ok_tag(self, judge_util.EvaluationTag('NR', 'Not Run'))
