# Testing Guide

This project uses `pytest` for regression testing.

## Prerequisites

- Python 3.11+
- `uv` package manager (recommended) or `pip`

## Configuration

The tests require a **separate test database** to ensure data safety.
You must set the `DATABASE_URL` environment variable before running tests.

**Safe patterns for Test DB URL:**
- Must contain `test`, `localhost`, `127.0.0.1`, or `.db` (SQLite).
- Example: `postgresql://user:pass@localhost:5432/gestao_tecnicos_test`
- Example: `sqlite:///test_database.db`

## Running Tests

### Using uv (Recommended)

```bash
# Run all tests quietly
uv run pytest -q

# Run with output
uv run pytest
```

### Using pip/python

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest

# Run tests
export DATABASE_URL="sqlite:///test_db.db"  # Linux/Mac
set DATABASE_URL=sqlite:///test_db.db       # Windows CMD
$env:DATABASE_URL="sqlite:///test_db.db"    # PowerShell

pytest
```

## Test Structure

- `tests/conftest.py`: Configuration and fixtures (App, DB).
- `tests/test_imports.py`: Verifies critical module imports (P0).
- `tests/test_financeiro_lote_transacao.py`: Verifies batch processing transaction isolation (P0).
- `tests/test_pricing_consistencia.py`: Verifies pricing logic consistency (Real-time vs Batch) (P0).
