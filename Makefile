.PHONY: test test-fast lint

test-fast:
	python3 -m pytest -x -q -m overnight_smoke tests/test_ralph_shell_helpers.py tests/test_bot_commands.py

test:
	python3 -m pytest tests/ -v

lint:
	bash -n ralph.sh
	python3 -c "import ast; ast.parse(open('scripts/ralph_bot.py').read())"
	python3 scripts/check_prompt_budgets.py
