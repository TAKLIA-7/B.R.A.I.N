# API Conventions: Antigravity E2E MCP Project 2

## 1. Design & Protocol
- REST endpoints adhere to OpenAPI 3.1 specifications via FastAPI.
- Agent tools follow FastMCP (Model Context Protocol) conventions.

## 2. Response & Error Formats
- Success responses return JSON objects with descriptive keys.
- Error responses return HTTP standard error codes with structured `detail` messages.
