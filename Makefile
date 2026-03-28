.PHONY: test lint

test:
	python3 -m pytest tests/ -v

lint:
	bash -n ralph.sh
	python3 -c "import ast; ast.parse(open('scripts/ralph_bot.py').read())"
	python3 scripts/check_prompt_budgets.py
