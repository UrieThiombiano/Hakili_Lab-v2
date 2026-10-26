# Hakili Lab — Makefile cross-platform (Windows + Unix)
# Windows : installer make via `winget install GnuWin32.Make` ou utiliser setup.ps1

.PHONY: setup run importer test lint clean

ifeq ($(OS),Windows_NT)
    PYTHON     = .venv\Scripts\python.exe
    PIP        = .venv\Scripts\pip.exe
else
    PYTHON     = .venv/bin/python
    PIP        = .venv/bin/pip
endif

setup:
	python -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Environnement pret. Copiez .env.example en .env et renseignez vos cles."

# API FastAPI — seule interface depuis le retrait de Django (D-CEO-42).
# Le frontend React se lance separement : cd frontend && npm run dev
run:
	$(PYTHON) -m uvicorn app.main:app --app-dir backend --reload

importer:
	$(PYTHON) backend/scripts/importer_referentiel.py

test:
	$(PYTHON) -m pytest tests/ -v --tb=short
	$(PYTHON) -m pytest backend/tests/ -v --tb=short

lint:
	$(PYTHON) -m ruff check src/ tests/ backend/app/ backend/tests/
	$(PYTHON) -m mypy src/ --ignore-missing-imports

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cache Python nettoye."
