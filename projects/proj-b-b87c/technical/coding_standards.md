# Coding Standards & Guidelines: Project Beta

## 1. Code Style
- Adhere to PEP 8 standards with strict type hinting.
- Use strict Pydantic v2 schemas (`extra='forbid'` where inputs must be constrained).

## 2. Testing & Verification Gate
- Code changes must be covered by automated tests (`pytest`).
- Fixes for defects cannot be marked verified without passing test proof.
