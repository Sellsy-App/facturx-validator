# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python package for validating Factur-X PDF invoices (European e-invoicing standard). Performs two-stage validation: XSD schema validation (structural) and Schematron validation (business rules) using XSLT 3.0. Currently supports **Factur-X 1.09 EXTENDED** profile.

Schematron validation runs **two** stylesheets over the same XML and merges the results: the EN16931/Factur-X rules, plus the **French CTC rules (BR-FR)** from the FNFE-MPE package `SCHEMATRONS_FR_CTC v1.4.0` (norme AFNOR XP Z12-012). The BR-FR rules add French mandate requirements (e.g. `BR-FR-02` invoice id charset, `BR-FR-05` mandatory legal notes PMT/PMD/AAB, `BR-FR-08` billing mode, `BR-FR-13` seller endpoint) and reproduce what the FNFE online validator reports.

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
  - `_collect_schematron(xml_str, xslt_paths=SCHEMATRON_XSLT_PATHS)` — shared helper: runs every stylesheet in `SCHEMATRON_XSLT_PATHS` under a single SaxonC processor and aggregates SVRL failed-asserts (errors) / successful-reports (warnings). `SCHEMATRON_XSLT_PATHS = [XSLT_PATH, BR_FR_XSLT_PATH]`.
- `facturx_validator/cli.py` — argparse CLI entry point, supports `--json` output
- `facturx_validator/data/factur_x_extended/` — Bundled XSD schemas and Factur-X Schematron XSLT files (v1.09)
- `facturx_validator/data/br_fr_ctc/` — Bundled French CTC Schematron (`.sch` source + compiled `.xslt`), FNFE v1.4.0

To bump the BR-FR rules, replace the files in `data/br_fr_ctc/` with the newer `Factur-X_1.09/EXTENDED` stylesheet from the FNFE package (the `.xslt` in its `2xslt/` folder is self-contained — no external `codedb`/`document()` dependency).

### Dependencies

- **pypdf** — PDF reading and attachment extraction
- **lxml** — XML parsing and XSD validation
- **saxonche** — SaxonC Home Edition for XSLT 3.0 Schematron processing

### Design notes

- Schema/XSLT files are resolved at runtime via `importlib.resources.files()` for package-relative access
- Schematron validation transforms XML through a compiled XSLT stylesheet, producing SVRL (Schematron Validation Report Language), then parses failed-assert (errors) and successful-report (warnings)
- Helper functions `_extract_field_from_location()` and `_extract_field_from_xsd_error()` extract field names from XPath locations and XSD error messages via regex
