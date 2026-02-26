.PHONY: test lint

test:
	python3 -m pytest tests/ -v

lint:
	python3 -c "import ast; ast.parse(open('scripts/ralph_bot.py').read())" && echo "AST OK"
