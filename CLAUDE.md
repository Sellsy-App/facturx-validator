# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python package for validating Factur-X PDF invoices (European e-invoicing standard). Performs two-stage validation: XSD schema validation (structural) and Schematron validation (business rules) using XSLT 3.0. Currently supports **Factur-X 1.09 EXTENDED** profile.

## Commands

```bash
# Install in dev mode
pip install -e .

# Run CLI
facturx-validator <path_to_pdf>
facturx-validator <path_to_pdf> --json

# No test suite or linter configured
```

## Architecture

**Validation pipeline:** PDF → XML extraction (pypdf) → XSD validation (lxml) → Schematron validation (saxonche/XSLT 3.0)

### Key modules

- `facturx_validator/facturx_validator.py` — Core logic with 4 public functions:
  - `extract_facturx_xml(pdf_stream)` — Extracts embedded XML from PDF attachments
  - `validate_xml(xml_str)` — XSD schema validation, returns human-readable string
  - `validate_schematron(xml_str)` — Schematron business rules via SaxonC XSLT 3.0, parses SVRL output
  - `validate_all(xml_str)` — Combined validation returning structured dict with `xsd_errors`, `xsd_warnings`, `schematron_errors`, `schematron_warnings` (each entry has `message`, `field`, and optionally `location`)
- `facturx_validator/cli.py` — argparse CLI entry point, supports `--json` output
- `facturx_validator/data/factur_x_extended/` — Bundled XSD schemas and Schematron XSLT files (v1.09)

### Dependencies

- **pypdf** — PDF reading and attachment extraction
- **lxml** — XML parsing and XSD validation
- **saxonche** — SaxonC Home Edition for XSLT 3.0 Schematron processing

### Design notes

- Schema/XSLT files are resolved at runtime via `importlib.resources.files()` for package-relative access
- Schematron validation transforms XML through a compiled XSLT stylesheet, producing SVRL (Schematron Validation Report Language), then parses failed-assert (errors) and successful-report (warnings)
- Helper functions `_extract_field_from_location()` and `_extract_field_from_xsd_error()` extract field names from XPath locations and XSD error messages via regex
