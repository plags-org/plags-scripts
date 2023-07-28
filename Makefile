MASTER_DIR = exercises/as-is
FORM_DIR = forms
TEST_DIR = tests
ANSWER_DIR = answers
RESULT_DIR = results

EXERCISES = $(basename $(notdir $(wildcard $(MASTER_DIR)/*.ipynb)))
MASTERS = $(addprefix $(MASTER_DIR)/, $(addsuffix .ipynb, $(EXERCISES)))
PREFILLS = $(addprefix $(MASTER_DIR)/, $(addsuffix .py, $(EXERCISES)))
ANSWERS = $(addprefix $(ANSWER_DIR)/, $(addsuffix .py, $(EXERCISES)))
TESTS = $(addprefix $(TEST_DIR)/, $(EXERCISES))

all:	conf.zip

conf.zip:	$(MASTERS) $(PREFILLS) test_mod.json
	mkdir -p $(FORM_DIR)
	python3 build_as_is.py -f $(FORM_DIR) -c judge_env.json -ae test_mod.json -ac -qc $(MASTERS)

$(PREFILLS):
	touch $@

test_mod.json:	$(TESTS)
	python3 -c "import json,os,sys; print(json.dumps({os.path.basename(path): [os.path.join(path, x) for x in sorted(os.listdir(path)) if x.endswith('.py')] for path in sorted(sys.argv[1:])}, ensure_ascii=False, indent=4))" $(TESTS) > test_mod.json

$(TESTS):	$(wildcard $@/*.py)
	mkdir -p $@
	if [ $(words $(wildcard $@/*.py)) -ne 0 ]; then touch -r $$(ls -dt $@ $@/*.py | head -n 1) $@; fi

test:	test_mod.json
	python3 -c "import json,os,sys; print(json.dumps({os.path.basename(path)[:-3]: path for path in sorted(sys.argv[1:]) if path.endswith('.py')}, ensure_ascii=False, indent=4))" $(ANSWERS) > answer_mod.json
	mkdir -p $(FORM_DIR).tmp $(RESULT_DIR)
	python3 build_as_is.py -f $(FORM_DIR).tmp -ae test_mod.json -ac answer_mod.json -qc -t $(RESULT_DIR) $(MASTERS)
	rm -fR $(FORM_DIR).tmp
	rm -f answer_mod.json

clean:
	rm -fR conf.zip conf test_mod.json answer_mod.json $(FORM_DIR) $(RESULT_DIR)

.PHONY: test clean
