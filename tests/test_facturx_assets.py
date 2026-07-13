"""Garde-fou de régression sur les assets de données Factur-X bundlés.

Vérifie qu'après la migration 1.08 -> 1.09 :
- le module pointe sur le XSD 1.09 ;
- les fichiers 1.09 sont présents et aucun fichier 1.08 ne subsiste ;
- le schéma XSD se construit (les imports relatifs ..._100.xsd se résolvent) ;
- le XSLT Schematron compile et s'exécute via SaxonC (skippé si saxonche absent).
"""
from pathlib import Path

import pytest
from lxml import etree

from facturx_validator import facturx_validator as fv

DATA_DIR = Path(fv.__file__).parent / "data" / "factur_x_extended"

EXPECTED_109_ASSETS = [
    "Factur-X_1.09_EXTENDED.sch",
    "Factur-X_1.09_EXTENDED.xsd",
    "Factur-X_1.09_EXTENDED_codedb.xml",
    "Factur-X_1.09_EXTENDED_urn_un_unece_uncefact_data_standard_QualifiedDataType_100.xsd",
    "Factur-X_1.09_EXTENDED_urn_un_unece_uncefact_data_standard_ReusableAggregateBusinessInformationEntity_100.xsd",
    "Factur-X_1.09_EXTENDED_urn_un_unece_uncefact_data_standard_UnqualifiedDataType_100.xsd",
]


def test_module_points_to_1_09_xsd():
    assert Path(str(fv.XSD_PATH)).name == "Factur-X_1.09_EXTENDED.xsd"


def test_1_09_assets_present():
    for name in EXPECTED_109_ASSETS:
        assert (DATA_DIR / name).is_file(), f"asset 1.09 manquant : {name}"


def test_no_1_08_assets_remain():
    leftovers = sorted(p.name for p in DATA_DIR.glob("*1.08*"))
    assert not leftovers, f"fichiers 1.08 résiduels : {leftovers}"


def test_xsd_schema_builds():
    parser = etree.XMLParser(load_dtd=True, no_network=False)
    doc = etree.parse(str(fv.XSD_PATH), parser)
    # Lève si un import relatif (..._100.xsd) ne se résout pas dans le dossier.
    etree.XMLSchema(doc)


def test_schematron_xslt_compiles_and_runs():
    saxonche = pytest.importorskip("saxonche")
    stub = (
        '<rsm:CrossIndustryInvoice '
        'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"/>'
    )
    with saxonche.PySaxonProcessor(license=False) as proc:
        xslt_proc = proc.new_xslt30_processor()
        xslt_exec = xslt_proc.compile_stylesheet(stylesheet_file=str(fv.XSLT_PATH))
        xml_doc = proc.parse_xml(xml_text=stub)
        xslt_exec.set_initial_match_selection(xdm_value=xml_doc)
        result = xslt_exec.apply_templates_returning_string()
        if isinstance(result, Path):
            result = result.read_text(encoding="utf-8")
        # Le transform doit produire un rapport SVRL bien formé.
        assert "schematron-output" in result


# --- Règles France BR-FR (réforme CTC, XP Z12-012 / FNFE v1.4.0) ---

EXPECTED_BR_FR_ASSETS = [
    "BR-FR-Flux2-Schematron-CII.sch",
    "BR-FR-Flux2-Schematron-CII.xslt",
    "BR-FR-Flux2-Schematron-CII_WARNING.sch",
    "BR-FR-Flux2-Schematron-CII_WARNING.xslt",
]

BR_FR_DIR = Path(fv.__file__).parent / "data" / "br_fr_ctc"


def test_br_fr_assets_present():
    for name in EXPECTED_BR_FR_ASSETS:
        assert (BR_FR_DIR / name).is_file(), f"asset BR-FR manquant : {name}"


def test_br_fr_xslt_is_in_schematron_pipeline():
    # Les deux feuilles (Factur-X EN16931 + BR-FR) doivent être appliquées.
    assert fv.BR_FR_XSLT_PATH in fv.SCHEMATRON_XSLT_PATHS
    assert fv.XSLT_PATH in fv.SCHEMATRON_XSLT_PATHS


def test_br_fr_variant_is_warning():
    # La variante _WARNING est active : la plupart des BR-FR sont non bloquantes.
    assert Path(str(fv.BR_FR_XSLT_PATH)).name == "BR-FR-Flux2-Schematron-CII_WARNING.xslt"


def test_br_fr_rules_are_detected_as_warnings():
    """Un XML minimal doit déclencher des règles BR-FR, prouvant que le
    Schématron France s'exécute — et qu'avec la variante _WARNING les règles
    flag=\"warning\" sont bien routées dans les avertissements."""
    pytest.importorskip("saxonche")
    stub = (
        '<rsm:CrossIndustryInvoice '
        'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"/>'
    )
    errors, warnings = fv._collect_schematron(stub, xslt_paths=[fv.BR_FR_XSLT_PATH])
    findings = errors + warnings
    assert any("BR-FR" in (f.get("message") or "") for f in findings), (
        "aucune règle BR-FR déclenchée : le Schématron France ne s'exécute pas"
    )
    assert any("BR-FR" in (w.get("message") or "") for w in warnings), (
        "aucune règle BR-FR en avertissement : le routage par flag ne fonctionne pas"
    )
