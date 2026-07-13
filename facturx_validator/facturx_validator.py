import pypdf
from lxml import etree
from importlib.resources import files
from pathlib import Path

XSD_PATH = files(__package__ + ".data.factur_x_extended").joinpath("Factur-X_1.09_EXTENDED.xsd")
XSLT_PATH = files(__package__ + ".data.factur_x_extended._XSLT_EXTENDED").joinpath("FACTUR-X_EXTENDED.xslt")
# Schématron des règles France (BR-FR) de la réforme CTC — norme XP Z12-012,
# distribué par la FNFE-MPE (package SCHEMATRONS_FR_CTC v1.4.0, profil Factur-X EXTENDED).
# Ces règles s'ajoutent à la validation EN16931/Factur-X ci-dessus.
# Variante _WARNING : la plupart des règles BR-FR sont émises en flag="warning"
# (classées dans schematron_warnings) au lieu de fatal, le temps de la transition.
# Pour redevenir strict, pointer sur "BR-FR-Flux2-Schematron-CII.xslt" (aussi bundlé).
BR_FR_XSLT_PATH = files(__package__ + ".data.br_fr_ctc").joinpath("BR-FR-Flux2-Schematron-CII_WARNING.xslt")

# Feuilles XSLT Schématron appliquées successivement au même XML.
SCHEMATRON_XSLT_PATHS = [XSLT_PATH, BR_FR_XSLT_PATH]

def extract_facturx_xml(pdf_stream):
    reader = pypdf.PdfReader(pdf_stream)
    if hasattr(reader, "attachments"):
        for filename, data in reader.attachments.items():
            if filename.lower().endswith('.xml'):
                if isinstance(data, list):
                    data = b"".join(data)
                return data.decode('utf-8')
    elif hasattr(reader, "embedded_files"):
        for file in reader.embedded_files:
            if file.name.lower().endswith('.xml'):
                if isinstance(file.data, list):
                    data = b"".join(file.data)
                else:
                    data = file.data
                return data.decode('utf-8')
    return None

def validate_xml(xml_str):
    xml_doc = etree.fromstring(xml_str.encode('utf-8'))
    parser = etree.XMLParser(load_dtd=True, no_network=False)
    with open(XSD_PATH, 'rb') as f:
        xsd_doc = etree.parse(f, parser)
    schema = etree.XMLSchema(xsd_doc)
    try:
        schema.assertValid(xml_doc)
        return 'Le fichier XML est valide selon le schéma XSD.'
    except etree.DocumentInvalid as e:
        return f'Erreur de validation XSD :\n{e}'

SVRL_NS = {'svrl': 'http://purl.oclc.org/dsdl/svrl'}


def _run_schematron_xslt(proc, xslt_path, xml_doc):
    """Applique une feuille XSLT Schématron au XML déjà parsé et renvoie
    (failed_asserts, successful_reports) sous forme de listes d'éléments SVRL."""
    xslt_proc = proc.new_xslt30_processor()
    xslt_exec = xslt_proc.compile_stylesheet(stylesheet_file=str(xslt_path))
    xslt_exec.set_initial_match_selection(xdm_value=xml_doc)
    result = xslt_exec.apply_templates_returning_string()
    if isinstance(result, Path):
        result = result.read_text(encoding='utf-8')
    svrl_doc = etree.fromstring(result.encode('utf-8'))
    failed_asserts = svrl_doc.xpath('//svrl:failed-assert', namespaces=SVRL_NS)
    successful_reports = svrl_doc.xpath('//svrl:successful-report', namespaces=SVRL_NS)
    return failed_asserts, successful_reports


def _svrl_message(elem):
    text_elem = elem.xpath('.//svrl:text', namespaces=SVRL_NS)
    message = text_elem[0].text if text_elem else 'Message non disponible'
    return (message or '').strip()


def _collect_schematron(xml_str, xslt_paths=SCHEMATRON_XSLT_PATHS):
    """Exécute toutes les feuilles Schématron et agrège erreurs/avertissements
    en dicts {location, field, message}. Une seule instance SaxonC est réutilisée."""
    from saxonche import PySaxonProcessor
    errors = []
    warnings = []
    with PySaxonProcessor(license=False) as proc:
        xml_doc = proc.parse_xml(xml_text=xml_str)
        for xslt_path in xslt_paths:
            failed_asserts, successful_reports = _run_schematron_xslt(proc, xslt_path, xml_doc)
            for assert_elem in failed_asserts:
                location = assert_elem.get('location', 'Location non spécifiée')
                entry = {
                    'location': location,
                    'field': _extract_field_from_location(location),
                    'message': _svrl_message(assert_elem),
                }
                # Le flag Schematron porte la sévérité : warning/information → avertissement,
                # tout le reste (fatal, error, absent) → erreur bloquante.
                if assert_elem.get('flag') in ('warning', 'information'):
                    warnings.append(entry)
                else:
                    errors.append(entry)
            for report_elem in successful_reports:
                location = report_elem.get('location', 'Location non spécifiée')
                warnings.append({
                    'location': location,
                    'field': _extract_field_from_location(location),
                    'message': _svrl_message(report_elem),
                })
    return errors, warnings


def validate_schematron(xml_str,):
    try:
        errors, warnings = _collect_schematron(xml_str)
        if not errors and not warnings:
            return 'Le fichier XML est valide selon le schématron.'
        result_parts = []
        if errors:
            result_parts.append(f"ERREURS SCHEMATRON ({len(errors)} trouvée(s)):")
            result_parts.extend(f"ERREUR à {e['location']}: {e['message']}" for e in errors)
        if warnings:
            if errors:
                result_parts.append("")
            result_parts.append(f"AVERTISSEMENTS SCHEMATRON ({len(warnings)} trouvé(s)):")
            result_parts.extend(f"AVERTISSEMENT à {w['location']}: {w['message']}" for w in warnings)
        return '\n'.join(result_parts)
    except Exception as e:
        return f'Erreur lors de la validation schématron : {e}'

def _extract_field_from_location(location):
    # Extrait le dernier nom d'élément du XPath (ex: .../*:Champ[...])
    import re
    matches = re.findall(r'/\*:(\w+)', location)
    if matches:
        return matches[-1]
    return None

def _extract_field_from_xsd_error(error_line):
    # Try to extract the field/element name from the XSD error message
    import re
    # Common pattern: Element 'FieldName': ...
    match = re.search(r"Element '([^']+)'", error_line)
    if match:
        return match.group(1)
    # Pattern: The attribute 'FieldName' is ...
    match = re.search(r"attribute '([^']+)'", error_line)
    if match:
        return match.group(1)
    # Pattern: Missing child element(s). Expected is ( FieldName )
    match = re.search(r'Expected is \( ([^ )]+)', error_line)
    if match:
        return match.group(1)
    return None

def validate_all(xml_str):
    # XSD
    xsd_errors = []
    xsd_warnings = []
    try:
        xml_doc = etree.fromstring(xml_str.encode('utf-8'))
        parser = etree.XMLParser(load_dtd=True, no_network=False)
        with XSD_PATH.open('rb') as f:
            xsd_doc = etree.parse(f, parser)
        schema = etree.XMLSchema(xsd_doc)
        try:
            schema.assertValid(xml_doc)
        except etree.DocumentInvalid as e:
            # On découpe les erreurs ligne par ligne
            for line in str(e).splitlines():
                if line.strip():
                    field = _extract_field_from_xsd_error(line.strip())
                    xsd_errors.append({'message': line.strip(), 'field': field})
    except Exception as e:
        xsd_errors.append({'message': f'Erreur lors de la validation XSD : {e}', 'field': None})

    # Schematron (EN16931/Factur-X + règles France BR-FR)
    schematron_errors = []
    schematron_warnings = []
    try:
        schematron_errors, schematron_warnings = _collect_schematron(xml_str)
    except Exception as e:
        schematron_errors.append({'message': f'Erreur lors de la validation schématron : {e}', 'field': None})

    return {
        'xsd_errors': xsd_errors,
        'xsd_warnings': xsd_warnings,
        'schematron_errors': schematron_errors,
        'schematron_warnings': schematron_warnings
    }
