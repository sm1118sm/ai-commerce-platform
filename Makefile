.PHONY: install run test test-integration check mysql-up mysql-down

install:
	python -m pip install -r requirements.txt

run:
	streamlit run app.py

test:
	python -m unittest discover -s tests -v

test-integration:
	test -n "$$STYLEPICK_TEST_DATABASE_URL"
	python -m unittest discover -s tests -v

mysql-up:
	docker compose up -d mysql

mysql-down:
	docker compose down

check:
	python -m compileall -q app.py src tests
	python -m unittest discover -s tests -v
