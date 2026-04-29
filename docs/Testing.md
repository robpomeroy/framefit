# Testing Guide

This project uses pytest for automated tests.

## Test Layout

- `tests/test_unit.py`: fast unit tests for pure helper logic
- `tests/test_integration.py`: file-based tests using temporary folders/images
- `tests/conftest.py`: shared fixtures for creating sample images

## Install Test Dependencies

From the project root:

```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run All Tests

```powershell
pytest -v
```

## Run a Specific Test File

```powershell
pytest tests\test_unit.py -v
pytest tests\test_integration.py -v
```

## Run Coverage

```powershell
pytest --cov=framefit --cov-report=term-missing
```

## What The Tests Validate

- Resize maths is proportionally correct
- EXIF handling resets orientation safely
- PNG/JPEG conversion behaviour is correct
- Dry-run mode does not create or delete files
- Corrupt image handling fails safely without crashing
- CLI argument validation exits with clear failures

## Notes

- Integration tests create temporary image files and clean them up
  automatically.
- Tests are designed for Windows but are generally cross-platform.
- Python 3.10+ is required. (The CI/CD pipeline uses 3.14.)

## Continuous Integration

Tests run automatically on GitHub Actions on every push to `main` and on every
pull request targeting `main`.

The CI matrix runs pytest across Ubuntu, macOS, and Windows using Python 3.14.

Workflow file: `.github/workflows/tests.yml`
