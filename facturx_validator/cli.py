#!/usr/bin/env python3
import sys
import json
import argparse
from facturx_validator import __version__, extract_facturx_xml, validate_xml, validate_schematron, validate_all

def main():
    parser = argparse.ArgumentParser(description="Valide un fichier PDF Factur-X")
    parser.add_argument("pdf_path", help="Chemin du fichier PDF")
    parser.add_argument("--json", action="store_true", help="Affiche le résultat en JSON")
    parser.add_argument("--version", action="version", version=f"facturx-validator {__version__}")
    args = parser.parse_args()

    with open(args.pdf_path, 'rb') as f:
        xml_str = extract_facturx_xml(f)
        if not xml_str:
            print("Aucun fichier XML Factur-X trouvé dans le PDF.")
            sys.exit(2)

        if args.json:
            result = validate_all(xml_str)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("=== VALIDATION XSD ===")
            print(validate_xml(xml_str))
            print("\n=== VALIDATION SCHEMATRON ===")
            print(validate_schematron(xml_str))

if __name__ == "__main__":
    main()
