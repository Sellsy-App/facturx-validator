import pypdf
from lxml import etree
from importlib.resources import files
from pathlib import Path
import re

XSD_PATH = files(__package__ + ".data.factur_x_extended").joinpath("Factur-X_1.08_EXTENDED.xsd")
XSLT_EXTENDED_PATH = files(__package__ + ".data.factur_x_extended._XSLT_EXTENDED").joinpath("FACTUR-X_EXTENDED.xslt")
XSLT_FLUX2_PATH = files(__package__ + ".data.flux2._XSLT").joinpath("20260216_BR-FR-Flux2-Schematron-CII_V1.3.0.xsl")

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

def _validate_schematron_with_xslt(xml_str, xslt_path, profile_name):
    try:
        from saxonche import PySaxonProcessor
        with PySaxonProcessor(license=False) as proc:
            xslt_proc = proc.new_xslt30_processor()
            xslt_exec = xslt_proc.compile_stylesheet(stylesheet_file=str(xslt_path))
            xml_doc = proc.parse_xml(xml_text=xml_str)
            xslt_exec.set_initial_match_selection(xdm_value=xml_doc)
            result = xslt_exec.apply_templates_returning_string()
            if isinstance(result, Path):
                result = result.read_text(encoding='utf-8')
            svrl_doc = etree.fromstring(result.encode('utf-8'))
            errors = []
            warnings = []
            svrl_ns = {'svrl': 'http://purl.oclc.org/dsdl/svrl'}

            failed_asserts = svrl_doc.xpath('//svrl:failed-assert', namespaces=svrl_ns)
            for assert_elem in failed_asserts:
                location = assert_elem.get('location', 'Location non spécifiée')
                text_elem = assert_elem.xpath('.//svrl:text', namespaces=svrl_ns)
                message = text_elem[0].text if text_elem else 'Message non disponible'
                errors.append({'location': location, 'field': _extract_field_from_location(location), 'message': message})

            successful_reports = svrl_doc.xpath('//svrl:successful-report', namespaces=svrl_ns)
            for report_elem in successful_reports:
                location = report_elem.get('location', 'Location non spécifiée')
                text_elem = report_elem.xpath('.//svrl:text', namespaces=svrl_ns)
                message = text_elem[0].text if text_elem else 'Message non disponible'
                warnings.append({'location': location, 'field': _extract_field_from_location(location), 'message': message})

            return errors, warnings
    except Exception as e:
        return [{'message': f'Erreur lors de la validation schématron {profile_name} : {e}', 'field': None}], []

def validate_schematron(xml_str):
    """
    Valide le XML avec les deux schematrons (EXTENDED et Flux2) et retourne un résumé texte.
    """
    results = []

    # Validation EXTENDED
    extended_errors, extended_warnings = _validate_schematron_with_xslt(xml_str, XSLT_EXTENDED_PATH, "EXTENDED")
    if not extended_errors and not extended_warnings:
        results.append('✓ Le fichier XML est valide selon le schématron EXTENDED.')
    else:
        if extended_errors:
            results.append(f"ERREURS SCHEMATRON EXTENDED ({len(extended_errors)} trouvée(s)):")
            for err in extended_errors:
                results.append(f"  ERREUR à {err['location']}: {err['message']}")
        if extended_warnings:
            if extended_errors:
                results.append("")
            results.append(f"AVERTISSEMENTS SCHEMATRON EXTENDED ({len(extended_warnings)} trouvé(s)):")
            for warn in extended_warnings:
                results.append(f"  AVERTISSEMENT à {warn['location']}: {warn['message']}")

    results.append("")

    # Validation CTC-FR
    ctc_fr_errors, ctc_fr_warnings = _validate_schematron_with_xslt(xml_str, XSLT_FLUX2_PATH, "Flux2")
    if not ctc_fr_errors and not ctc_fr_warnings:
        results.append('✓ Le fichier XML est valide selon le schématron Flux2.')
    else:
        if ctc_fr_errors:
            results.append(f"ERREURS SCHEMATRON Flux2 ({len(ctc_fr_errors)} trouvée(s)):")
            for err in ctc_fr_errors:
                results.append(f"  ERREUR à {err['location']}: {err['message']}")
        if ctc_fr_warnings:
            if ctc_fr_errors:
                results.append("")
            results.append(f"AVERTISSEMENTS SCHEMATRON Flux2 ({len(ctc_fr_warnings)} trouvé(s)):")
            for warn in ctc_fr_warnings:
                results.append(f"  AVERTISSEMENT à {warn['location']}: {warn['message']}")

    return '\n'.join(results)

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

    # Schematron EXTENDED
    schematron_errors, schematron_warnings = _validate_schematron_with_xslt(xml_str, XSLT_EXTENDED_PATH, "EXTENDED")

    # Schematron CTC-FR
    schematron_flux2_errors, schematron_flux2_warnings = _validate_schematron_with_xslt(xml_str, XSLT_FLUX2_PATH, "Flux2")

    return {
        'xsd_errors': xsd_errors,
        'xsd_warnings': xsd_warnings,
        'schematron_errors': schematron_errors,
        'schematron_warnings': schematron_warnings,
        'schematron_flux2_errors': schematron_flux2_errors,
        'schematron_flux2_warnings': schematron_flux2_warnings
    }
