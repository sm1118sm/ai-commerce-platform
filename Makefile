.PHONY: install run start status logs stop test test-integration check mysql-up mysql-down

install:
	python -m pip install -r requirements.txt

run:
	streamlit run app.py

start:
	docker compose up -d --build

status:
	docker compose ps

logs:
	docker compose logs -f app

stop:
	docker compose down

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
