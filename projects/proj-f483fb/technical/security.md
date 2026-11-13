# Security Policy & Conventions: Handover Project

## 1. Authentication & Secret Management
- API Keys and JWT signing secrets must be managed through `.env`.
- No raw secrets in version control or generated Markdown files.

## 2. SQL & Query Security
- All database operations must use parameterized queries (`%s` placeholders).
- Never use direct string interpolation for database queries.
