.PHONY: install run test check

install:
	python -m pip install -r requirements.txt

run:
	streamlit run app.py

test:
	python -m unittest discover -s tests -v

check:
	python -m compileall -q app.py src tests
	python -m unittest discover -s tests -v

