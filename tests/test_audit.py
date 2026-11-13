"""Regression tests with independent fixed phrase oracles."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from id_document_extraction_claim_audit.audit import audit, evidence, paragraphs, normalize
from id_document_extraction_claim_audit.__main__ import main
from id_document_extraction_claim_audit import phrases

EXPECTED_POSITIVE = ('id document extraction',
 'extract id documents',
 'extracts id documents',
 'extracting id documents',
 'extract id document',
 'extracts id document',
 'extracting id document',
 'identity document extraction',
 'extract identity documents',
 'extracts identity documents',
 'extracting identity documents',
 'extract identity document',
 'extracts identity document',
 'extracting identity document',
 'passport extraction',
 'extract passports',
 'extracts passports',
 'extracting passports',
 'extract passport',
 'extracts passport',
 'extracting passport',
 'passport data extraction',
 'extract passport data',
 'extracts passport data',
 'extracting passport data',
 'id card extraction',
 'extract id cards',
 'extracts id cards',
 'extracting id cards',
 'extract id card',
 'extracts id card',
 'extracting id card',
 'driver license extraction',
 'extract driver licenses',
 'extracts driver licenses',
 'extracting driver licenses',
 'extract driver license',
 'extracts driver license',
 'extracting driver license',
 'mrz extraction',
 'extract mrz',
 'extracts mrz',
 'extracting mrz',
 'mrz parsing',
 'id document parsing',
 'id document parser',
 'passport parsing',
 'passport parser',
 'parse passports',
 'parses passports')
EXPECTED_NEGATIVE = ('no id document extraction',
 'does not extract id documents',
 'does not extract id document',
 'does not support id document extraction',
 'without id document extraction',
 'no passport extraction',
 'does not extract passports',
 'does not extract passport',
 'does not support passport extraction',
 'no identity document extraction',
 'does not extract identity documents',
 'does not extract identity document',
 'id document extraction not supported',
 'no id card extraction',
 'does not extract id cards',
 'does not extract id card',
 'no driver license extraction',
 'does not extract driver licenses',
 'does not extract driver license',
 'no mrz extraction',
 'does not extract mrz',
 'no passport parser',
 'does not parse passports',
 'does not parse passport')
EXPECTED_GENERIC = ('extract_id_document',
 'extract_id_documents',
 'parse_id_document',
 'parse_id_documents',
 'extract_passport',
 'extract_passports',
 'parse_passport',
 'parse_passports',
 'extract_passport_data',
 'passport_extraction',
 'passport_extractor',
 'passport_parser',
 'extract_id_card',
 'extract_id_cards',
 'parse_id_card',
 'id_document_extraction',
 'id_document_extractor',
 'extract_driver_license',
 'extract_driver_licenses',
 'parse_driver_license',
 'driver_license_extraction',
 'extract_mrz',
 'parse_mrz',
 'mrz_extraction')

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_phrase_oracle(self):
        tree = ast.parse(Path(phrases.__file__).read_text(encoding='utf-8'))
        tables = {node.targets[0].id: ast.literal_eval(node.value)
                  for node in tree.body if isinstance(node, ast.Assign)}
        for name, expected in (('IDDOCUMENTEXTRACTION', EXPECTED_POSITIVE),
                               ('NOIDDOCUMENTEXTRACTION', EXPECTED_NEGATIVE),
                               ('GENERIC_NAMES', EXPECTED_GENERIC)):
            actual = tables[name]
            self.assertEqual(tuple(map(normalize, actual)), tuple(map(normalize, expected)))
            self.assertEqual(len(actual), len(set(actual)))

    def test_findings_and_threshold(self):
        self.put('README.md', 'extract passports')
        code, out = self.cli('audit', str(self.root), '--json')
        result = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'FAIL')
        finding = result['findings'][0]
        self.assertEqual(finding['id'], 'documented-id-document-extraction-claim-false')
        self.assertEqual(finding['severity'], 'HIGH')
        self.assertTrue(finding['message'])
        self.put('tests/probe.py', 'x.extract_passport()')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
        self.assertEqual(self.cli('audit', str(self.root), '--fail-on', 'medium')[0], 2)
        self.put('app.py', 'x.extract_passport()')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', 'does not extract passports')
        result = audit(self.root)
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['id'], 'documented-no-id-document-extraction-claim-false')
        self.assertEqual(self.cli('audit', str(self.root))[0], 2)

    def test_docs_and_no_source(self):
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', 'no passport extraction')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        for fence in ('```', '~~~', '   ````'):
            self.put('README.md', fence+'\nextract passports\n'+fence+'\n')
            self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', '`extract passports`')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.put('README.md', 'safe')
        self.put('nested/docs/guide.md', "doesn't extract passports")
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('nested/docs/guide.md', 'EXTRACT-PASSPORTS')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'nested')[0], 0)

    def test_scope_and_exclusions(self):
        self.put('README.md', 'extract passports')
        self.put('one.py', 'import mindee\nmindee.Client()')
        self.put('two.py', 'x.parse(product.PassportV1)')
        for folder in ('fixtures', 'docs', 'examples'):
            self.put(folder+'/app.py', 'x.extract_passport()')
        target = self.root/'fixtures/app.py'
        (self.root/'linked.py').symlink_to(target)
        (self.root/'linked_dir').symlink_to(self.root/'fixtures', target_is_directory=True)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        for name in ('test_app.py', 'app_test.py', 'tests/app.py'):
            self.put(name, 'x.extract_passport()')
        result = audit(self.root)
        self.assertEqual(len(result['test_evidence']), 3)
        self.assertFalse(result['evidence'])

    def test_cli(self):
        self.assertEqual(self.cli('--version'), (0, '0.1.0\n'))
        for args in ([], ['bogus'], ['audit', '--fail-on', 'MEDIUM'], ['audit', '/nonexistent-r190']):
            self.assertEqual(self.cli(*args)[0], 1)
        result = subprocess.run([sys.executable, '-m', 'id_document_extraction_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, '0.1.0\n'))


    def test_all_phrase_matches(self):
        for phrase in EXPECTED_POSITIVE:
            self.put('README.md', phrase)
            self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH', phrase)
        for phrase in EXPECTED_NEGATIVE:
            self.put('README.md', phrase)
            self.assertEqual(audit(self.root)['verdict'], 'PASS', phrase)
            self.put('app.py', 'x.extract_passport()')
            result = audit(self.root)
            self.assertEqual(len(result['findings']), 1, phrase)
            self.assertEqual(result['findings'][0]['id'],
                             'documented-no-id-document-extraction-claim-false', phrase)
            (self.root / 'app.py').unlink()

    def test_azure_pair_split(self):
        self.put('README.md', 'extract passports')
        self.put('client.py', 'from azure.ai.formrecognizer import DocumentAnalysisClient\nDocumentAnalysisClient()')
        self.put('operation.py', 'x.begin_analyze_document("prebuilt-idDocument")')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')

    def test_verbose_and_repeated_ignore(self):
        self.put('README.md', 'extract passports')
        self.put('a/one.py', 'x.extract_passport()')
        self.put('b/two.py', 'x.extract_passport()')
        code, out = self.cli('audit', str(self.root), '--verbose')
        self.assertEqual(code, 0)
        self.assertIn('Production evidence:', out)
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'a', '--ignore', 'b')[0], 2)


GOOD_CASES = ['import mindee\nc=mindee.Client()\nc.parse(PassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.PassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.PassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.PassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(TypePassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.TypePassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.TypePassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.TypePassportV1)',
 'import mindee\nc=mindee.Client()\nc.parse(InternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.InternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.InternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.InternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(TypeInternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.TypeInternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.TypeInternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.TypeInternationalIdV2)',
 'import mindee\nc=mindee.Client()\nc.parse(DriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.DriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.DriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.DriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(TypeDriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.TypeDriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.TypeDriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.TypeDriverLicenseV1)',
 'import mindee\nc=mindee.Client()\nc.parse(IdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.IdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.IdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.IdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(TypeIdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.TypeIdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.TypeIdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.TypeIdCardV1)',
 'import mindee\nc=mindee.Client()\nc.parse(IdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.IdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.IdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.IdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(TypeIdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.TypeIdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.us.TypeIdCardV2)',
 'import mindee\nc=mindee.Client()\nc.parse(product.fr.TypeIdCardV2)',
 'from mindee import Client as C\nC()\nx.parse(documents.TypePassportV1)',
 'import mindee as m\nm.Client()\nx.parse(PassportV1)',
 'from mindee import Client\nC=Client\nC()\nx.parse(product.PassportV1)',
 'from mindee import Client\nC: object = Client\nC()\nx.parse(product.PassportV1)',
 'from azure.ai.formrecognizer import DocumentAnalysisClient as C\n'
 'C()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'import azure.ai.formrecognizer\n'
 'azure.ai.formrecognizer.DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'import azure.ai.formrecognizer as az\n'
 'az.DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'from azure.ai.formrecognizer import DocumentAnalysisClient as C\n'
 'C()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.formrecognizer\n'
 'azure.ai.formrecognizer.DocumentAnalysisClient()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.formrecognizer as az\n'
 'az.DocumentAnalysisClient()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'from azure.ai.formrecognizer import DocumentAnalysisClient as C\n'
 'C()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'import azure.ai.formrecognizer\n'
 'azure.ai.formrecognizer.DocumentAnalysisClient()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'import azure.ai.formrecognizer as az\n'
 'az.DocumentAnalysisClient()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'from azure.ai.formrecognizer import DocumentAnalysisClient as C\n'
 'C()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.formrecognizer\n'
 'azure.ai.formrecognizer.DocumentAnalysisClient()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.formrecognizer as az\n'
 'az.DocumentAnalysisClient()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'from azure.ai.documentintelligence import DocumentIntelligenceClient as C\n'
 'C()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'import azure.ai.documentintelligence\n'
 'azure.ai.documentintelligence.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'import azure.ai.documentintelligence as az\n'
 'az.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument", doc)',
 'from azure.ai.documentintelligence import DocumentIntelligenceClient as C\n'
 'C()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.documentintelligence\n'
 'azure.ai.documentintelligence.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.documentintelligence as az\n'
 'az.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document(model_id="prebuilt-idDocument", document=doc)',
 'from azure.ai.documentintelligence import DocumentIntelligenceClient as C\n'
 'C()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'import azure.ai.documentintelligence\n'
 'azure.ai.documentintelligence.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'import azure.ai.documentintelligence as az\n'
 'az.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document_from_url("prebuilt-idDocument", doc)',
 'from azure.ai.documentintelligence import DocumentIntelligenceClient as C\n'
 'C()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.documentintelligence\n'
 'azure.ai.documentintelligence.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'import azure.ai.documentintelligence as az\n'
 'az.DocumentIntelligenceClient()\n'
 'x.begin_analyze_document_from_url(model_id="prebuilt-idDocument", document=doc)',
 'import boto3\nx.analyze_id(DocumentPages=pages)',
 'from boto3 import client as C\nx.analyze_id()',
 'import boto3 as b\nx.analyze_id()',
 'import passporteye\npassporteye.read_mrz(file)',
 'from passporteye import read_mrz\nread_mrz(file)',
 'from passporteye import read_mrz as read\nread(file)',
 'import passporteye as p\np.read_mrz(file)',
 'x.extract_id_document(doc)',
 'from custom import extract_id_document\nextract_id_document(doc)',
 'from custom import extract_id_document as operation\noperation(doc)',
 'x.extract_id_documents(doc)',
 'from custom import extract_id_documents\nextract_id_documents(doc)',
 'from custom import extract_id_documents as operation\noperation(doc)',
 'x.parse_id_document(doc)',
 'from custom import parse_id_document\nparse_id_document(doc)',
 'from custom import parse_id_document as operation\noperation(doc)',
 'x.parse_id_documents(doc)',
 'from custom import parse_id_documents\nparse_id_documents(doc)',
 'from custom import parse_id_documents as operation\noperation(doc)',
 'x.extract_passport(doc)',
 'from custom import extract_passport\nextract_passport(doc)',
 'from custom import extract_passport as operation\noperation(doc)',
 'x.extract_passports(doc)',
 'from custom import extract_passports\nextract_passports(doc)',
 'from custom import extract_passports as operation\noperation(doc)',
 'x.parse_passport(doc)',
 'from custom import parse_passport\nparse_passport(doc)',
 'from custom import parse_passport as operation\noperation(doc)',
 'x.parse_passports(doc)',
 'from custom import parse_passports\nparse_passports(doc)',
 'from custom import parse_passports as operation\noperation(doc)',
 'x.extract_passport_data(doc)',
 'from custom import extract_passport_data\nextract_passport_data(doc)',
 'from custom import extract_passport_data as operation\noperation(doc)',
 'x.passport_extraction(doc)',
 'from custom import passport_extraction\npassport_extraction(doc)',
 'from custom import passport_extraction as operation\noperation(doc)',
 'x.passport_extractor(doc)',
 'from custom import passport_extractor\npassport_extractor(doc)',
 'from custom import passport_extractor as operation\noperation(doc)',
 'x.passport_parser(doc)',
 'from custom import passport_parser\npassport_parser(doc)',
 'from custom import passport_parser as operation\noperation(doc)',
 'x.extract_id_card(doc)',
 'from custom import extract_id_card\nextract_id_card(doc)',
 'from custom import extract_id_card as operation\noperation(doc)',
 'x.extract_id_cards(doc)',
 'from custom import extract_id_cards\nextract_id_cards(doc)',
 'from custom import extract_id_cards as operation\noperation(doc)',
 'x.parse_id_card(doc)',
 'from custom import parse_id_card\nparse_id_card(doc)',
 'from custom import parse_id_card as operation\noperation(doc)',
 'x.id_document_extraction(doc)',
 'from custom import id_document_extraction\nid_document_extraction(doc)',
 'from custom import id_document_extraction as operation\noperation(doc)',
 'x.id_document_extractor(doc)',
 'from custom import id_document_extractor\nid_document_extractor(doc)',
 'from custom import id_document_extractor as operation\noperation(doc)',
 'x.extract_driver_license(doc)',
 'from custom import extract_driver_license\nextract_driver_license(doc)',
 'from custom import extract_driver_license as operation\noperation(doc)',
 'x.extract_driver_licenses(doc)',
 'from custom import extract_driver_licenses\nextract_driver_licenses(doc)',
 'from custom import extract_driver_licenses as operation\noperation(doc)',
 'x.parse_driver_license(doc)',
 'from custom import parse_driver_license\nparse_driver_license(doc)',
 'from custom import parse_driver_license as operation\noperation(doc)',
 'x.driver_license_extraction(doc)',
 'from custom import driver_license_extraction\ndriver_license_extraction(doc)',
 'from custom import driver_license_extraction as operation\noperation(doc)',
 'x.extract_mrz(doc)',
 'from custom import extract_mrz\nextract_mrz(doc)',
 'from custom import extract_mrz as operation\noperation(doc)',
 'x.parse_mrz(doc)',
 'from custom import parse_mrz\nparse_mrz(doc)',
 'from custom import parse_mrz as operation\noperation(doc)',
 'x.mrz_extraction(doc)',
 'from custom import mrz_extraction\nmrz_extraction(doc)',
 'from custom import mrz_extraction as operation\noperation(doc)']
BAD_CASES = ['import mindee',
 'import boto3',
 'import passporteye',
 'import azure.ai.formrecognizer',
 'import azure.ai.documentintelligence',
 'import mindee\nmindee.Client()',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\nDocumentAnalysisClient()',
 'import passporteye\npassporteye.MRZPipeline(file)',
 'from mrz.checker.td3 import TD3Code\nTD3Code(text)',
 'import re\n'
 'text=pytesseract.image_to_string(image)\n'
 'fields={"name":re.search("Name: (.*)",text)}',
 'import subprocess\nsubprocess.run(["mindee", "parse", "passport"])',
 'import subprocess\nsubprocess.run(["mrz", "passport.png"])',
 '# x.extract_passport()\ns="x.extract_passport()"',
 'x.extract_passport',
 'x.extract_passport(',
 'extract_passport(doc)',
 'read_mrz(doc)',
 'import mindee\nx.parse(PassportV1)',
 'x.analyze_id()',
 'x.read_mrz()',
 'x.begin_analyze_document("prebuilt-idDocument")',
 'from mindee import Client\nwith context() as Client:\n Client()\nx.parse(PassportV1)',
 'from mindee import Client\nClient: object = other\nClient()\nx.parse(PassportV1)',
 'from mindee import Client\nClient = other\nClient()\nx.parse(PassportV1)',
 'from mindee import Client\n'
 'async def f():\n'
 ' async with context() as Client:\n'
 '  Client()\n'
 'x.parse(PassportV1)',
 'import mindee\nmindee.Client()\nx.parse(product.InvoiceV4)',
 'import mindee\nmindee.Client()\nx.parse(product.ReceiptV5)',
 'import mindee\nmindee.Client()\nx.parse(product.BankCheckV1)',
 'import mindee\nmindee.Client()\nx.parse(product.FinancialDocumentV1)',
 'import mindee\nmindee.Client()\nx.parse(product.CustomV1)',
 'import mindee\nmindee.Client()\nx.parse(product.Other)',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-invoice")',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-receipt")',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-layout")',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-read")',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("other")',
 'import boto3\nx.analyze_document()',
 'import boto3\nx.detect_document_text()',
 'import boto3\nx.analyze_expense()',
 'import boto3\nx.get_expense_analysis()',
 'import boto3\nx.start_document_analysis()',
 'import pdfplumber\npdfplumber.extract_text(doc)',
 'import pdfplumber\npdfplumber.extract_table(doc)',
 'import pdfplumber\npdfplumber.extract_tables(doc)',
 'import pdfplumber\npdfplumber.find_table(doc)',
 'import pdfplumber\npdfplumber.find_tables(doc)',
 'import fitz\nfitz.extract_text(doc)',
 'import fitz\nfitz.find_tables(doc)',
 'import pypdf\npypdf.extract_text(doc)',
 'import PyPDF2\nPyPDF2.extract_text(doc)',
 'import pdfminer\npdfminer.extract_text(doc)',
 'import pytesseract\npytesseract.image_to_string(doc)',
 'import pandas\npandas.read_csv(doc)',
 'import pandas\npandas.read_excel(doc)',
 'import camelot\ncamelot.read_pdf(doc)',
 'import tabula\ntabula.read_pdf(doc)',
 'import tabula\ntabula.convert_into(doc)',
 'from custom import extract_id_document as op\n'
 'op(doc)\n'
 'x.extract_id_document(doc)\n'
 'def extract_id_document(): pass',
 'from custom import extract_id_document as op\n'
 'op(doc)\n'
 'x.extract_id_document(doc)\n'
 'class Container:\n'
 ' def extract_id_document(self): pass',
 'from custom import extract_id_document as op\n'
 'op(doc)\n'
 'x.extract_id_document(doc)\n'
 'class extract_id_document: pass',
 'from custom import extract_id_documents as op\n'
 'op(doc)\n'
 'x.extract_id_documents(doc)\n'
 'def extract_id_documents(): pass',
 'from custom import extract_id_documents as op\n'
 'op(doc)\n'
 'x.extract_id_documents(doc)\n'
 'class Container:\n'
 ' def extract_id_documents(self): pass',
 'from custom import extract_id_documents as op\n'
 'op(doc)\n'
 'x.extract_id_documents(doc)\n'
 'class extract_id_documents: pass',
 'from custom import parse_id_document as op\n'
 'op(doc)\n'
 'x.parse_id_document(doc)\n'
 'def parse_id_document(): pass',
 'from custom import parse_id_document as op\n'
 'op(doc)\n'
 'x.parse_id_document(doc)\n'
 'class Container:\n'
 ' def parse_id_document(self): pass',
 'from custom import parse_id_document as op\n'
 'op(doc)\n'
 'x.parse_id_document(doc)\n'
 'class parse_id_document: pass',
 'from custom import parse_id_documents as op\n'
 'op(doc)\n'
 'x.parse_id_documents(doc)\n'
 'def parse_id_documents(): pass',
 'from custom import parse_id_documents as op\n'
 'op(doc)\n'
 'x.parse_id_documents(doc)\n'
 'class Container:\n'
 ' def parse_id_documents(self): pass',
 'from custom import parse_id_documents as op\n'
 'op(doc)\n'
 'x.parse_id_documents(doc)\n'
 'class parse_id_documents: pass',
 'from custom import extract_passport as op\n'
 'op(doc)\n'
 'x.extract_passport(doc)\n'
 'def extract_passport(): pass',
 'from custom import extract_passport as op\n'
 'op(doc)\n'
 'x.extract_passport(doc)\n'
 'class Container:\n'
 ' def extract_passport(self): pass',
 'from custom import extract_passport as op\n'
 'op(doc)\n'
 'x.extract_passport(doc)\n'
 'class extract_passport: pass',
 'from custom import extract_passports as op\n'
 'op(doc)\n'
 'x.extract_passports(doc)\n'
 'def extract_passports(): pass',
 'from custom import extract_passports as op\n'
 'op(doc)\n'
 'x.extract_passports(doc)\n'
 'class Container:\n'
 ' def extract_passports(self): pass',
 'from custom import extract_passports as op\n'
 'op(doc)\n'
 'x.extract_passports(doc)\n'
 'class extract_passports: pass',
 'from custom import parse_passport as op\n'
 'op(doc)\n'
 'x.parse_passport(doc)\n'
 'def parse_passport(): pass',
 'from custom import parse_passport as op\n'
 'op(doc)\n'
 'x.parse_passport(doc)\n'
 'class Container:\n'
 ' def parse_passport(self): pass',
 'from custom import parse_passport as op\n'
 'op(doc)\n'
 'x.parse_passport(doc)\n'
 'class parse_passport: pass',
 'from custom import parse_passports as op\n'
 'op(doc)\n'
 'x.parse_passports(doc)\n'
 'def parse_passports(): pass',
 'from custom import parse_passports as op\n'
 'op(doc)\n'
 'x.parse_passports(doc)\n'
 'class Container:\n'
 ' def parse_passports(self): pass',
 'from custom import parse_passports as op\n'
 'op(doc)\n'
 'x.parse_passports(doc)\n'
 'class parse_passports: pass',
 'from custom import extract_passport_data as op\n'
 'op(doc)\n'
 'x.extract_passport_data(doc)\n'
 'def extract_passport_data(): pass',
 'from custom import extract_passport_data as op\n'
 'op(doc)\n'
 'x.extract_passport_data(doc)\n'
 'class Container:\n'
 ' def extract_passport_data(self): pass',
 'from custom import extract_passport_data as op\n'
 'op(doc)\n'
 'x.extract_passport_data(doc)\n'
 'class extract_passport_data: pass',
 'from custom import passport_extraction as op\n'
 'op(doc)\n'
 'x.passport_extraction(doc)\n'
 'def passport_extraction(): pass',
 'from custom import passport_extraction as op\n'
 'op(doc)\n'
 'x.passport_extraction(doc)\n'
 'class Container:\n'
 ' def passport_extraction(self): pass',
 'from custom import passport_extraction as op\n'
 'op(doc)\n'
 'x.passport_extraction(doc)\n'
 'class passport_extraction: pass',
 'from custom import passport_extractor as op\n'
 'op(doc)\n'
 'x.passport_extractor(doc)\n'
 'def passport_extractor(): pass',
 'from custom import passport_extractor as op\n'
 'op(doc)\n'
 'x.passport_extractor(doc)\n'
 'class Container:\n'
 ' def passport_extractor(self): pass',
 'from custom import passport_extractor as op\n'
 'op(doc)\n'
 'x.passport_extractor(doc)\n'
 'class passport_extractor: pass',
 'from custom import passport_parser as op\n'
 'op(doc)\n'
 'x.passport_parser(doc)\n'
 'def passport_parser(): pass',
 'from custom import passport_parser as op\n'
 'op(doc)\n'
 'x.passport_parser(doc)\n'
 'class Container:\n'
 ' def passport_parser(self): pass',
 'from custom import passport_parser as op\n'
 'op(doc)\n'
 'x.passport_parser(doc)\n'
 'class passport_parser: pass',
 'from custom import extract_id_card as op\n'
 'op(doc)\n'
 'x.extract_id_card(doc)\n'
 'def extract_id_card(): pass',
 'from custom import extract_id_card as op\n'
 'op(doc)\n'
 'x.extract_id_card(doc)\n'
 'class Container:\n'
 ' def extract_id_card(self): pass',
 'from custom import extract_id_card as op\n'
 'op(doc)\n'
 'x.extract_id_card(doc)\n'
 'class extract_id_card: pass',
 'from custom import extract_id_cards as op\n'
 'op(doc)\n'
 'x.extract_id_cards(doc)\n'
 'def extract_id_cards(): pass',
 'from custom import extract_id_cards as op\n'
 'op(doc)\n'
 'x.extract_id_cards(doc)\n'
 'class Container:\n'
 ' def extract_id_cards(self): pass',
 'from custom import extract_id_cards as op\n'
 'op(doc)\n'
 'x.extract_id_cards(doc)\n'
 'class extract_id_cards: pass',
 'from custom import parse_id_card as op\n'
 'op(doc)\n'
 'x.parse_id_card(doc)\n'
 'def parse_id_card(): pass',
 'from custom import parse_id_card as op\n'
 'op(doc)\n'
 'x.parse_id_card(doc)\n'
 'class Container:\n'
 ' def parse_id_card(self): pass',
 'from custom import parse_id_card as op\n'
 'op(doc)\n'
 'x.parse_id_card(doc)\n'
 'class parse_id_card: pass',
 'from custom import id_document_extraction as op\n'
 'op(doc)\n'
 'x.id_document_extraction(doc)\n'
 'def id_document_extraction(): pass',
 'from custom import id_document_extraction as op\n'
 'op(doc)\n'
 'x.id_document_extraction(doc)\n'
 'class Container:\n'
 ' def id_document_extraction(self): pass',
 'from custom import id_document_extraction as op\n'
 'op(doc)\n'
 'x.id_document_extraction(doc)\n'
 'class id_document_extraction: pass',
 'from custom import id_document_extractor as op\n'
 'op(doc)\n'
 'x.id_document_extractor(doc)\n'
 'def id_document_extractor(): pass',
 'from custom import id_document_extractor as op\n'
 'op(doc)\n'
 'x.id_document_extractor(doc)\n'
 'class Container:\n'
 ' def id_document_extractor(self): pass',
 'from custom import id_document_extractor as op\n'
 'op(doc)\n'
 'x.id_document_extractor(doc)\n'
 'class id_document_extractor: pass',
 'from custom import extract_driver_license as op\n'
 'op(doc)\n'
 'x.extract_driver_license(doc)\n'
 'def extract_driver_license(): pass',
 'from custom import extract_driver_license as op\n'
 'op(doc)\n'
 'x.extract_driver_license(doc)\n'
 'class Container:\n'
 ' def extract_driver_license(self): pass',
 'from custom import extract_driver_license as op\n'
 'op(doc)\n'
 'x.extract_driver_license(doc)\n'
 'class extract_driver_license: pass',
 'from custom import extract_driver_licenses as op\n'
 'op(doc)\n'
 'x.extract_driver_licenses(doc)\n'
 'def extract_driver_licenses(): pass',
 'from custom import extract_driver_licenses as op\n'
 'op(doc)\n'
 'x.extract_driver_licenses(doc)\n'
 'class Container:\n'
 ' def extract_driver_licenses(self): pass',
 'from custom import extract_driver_licenses as op\n'
 'op(doc)\n'
 'x.extract_driver_licenses(doc)\n'
 'class extract_driver_licenses: pass',
 'from custom import parse_driver_license as op\n'
 'op(doc)\n'
 'x.parse_driver_license(doc)\n'
 'def parse_driver_license(): pass',
 'from custom import parse_driver_license as op\n'
 'op(doc)\n'
 'x.parse_driver_license(doc)\n'
 'class Container:\n'
 ' def parse_driver_license(self): pass',
 'from custom import parse_driver_license as op\n'
 'op(doc)\n'
 'x.parse_driver_license(doc)\n'
 'class parse_driver_license: pass',
 'from custom import driver_license_extraction as op\n'
 'op(doc)\n'
 'x.driver_license_extraction(doc)\n'
 'def driver_license_extraction(): pass',
 'from custom import driver_license_extraction as op\n'
 'op(doc)\n'
 'x.driver_license_extraction(doc)\n'
 'class Container:\n'
 ' def driver_license_extraction(self): pass',
 'from custom import driver_license_extraction as op\n'
 'op(doc)\n'
 'x.driver_license_extraction(doc)\n'
 'class driver_license_extraction: pass',
 'from custom import extract_mrz as op\nop(doc)\nx.extract_mrz(doc)\ndef extract_mrz(): pass',
 'from custom import extract_mrz as op\n'
 'op(doc)\n'
 'x.extract_mrz(doc)\n'
 'class Container:\n'
 ' def extract_mrz(self): pass',
 'from custom import extract_mrz as op\nop(doc)\nx.extract_mrz(doc)\nclass extract_mrz: pass',
 'from custom import parse_mrz as op\nop(doc)\nx.parse_mrz(doc)\ndef parse_mrz(): pass',
 'from custom import parse_mrz as op\n'
 'op(doc)\n'
 'x.parse_mrz(doc)\n'
 'class Container:\n'
 ' def parse_mrz(self): pass',
 'from custom import parse_mrz as op\nop(doc)\nx.parse_mrz(doc)\nclass parse_mrz: pass',
 'from custom import mrz_extraction as op\n'
 'op(doc)\n'
 'x.mrz_extraction(doc)\n'
 'def mrz_extraction(): pass',
 'from custom import mrz_extraction as op\n'
 'op(doc)\n'
 'x.mrz_extraction(doc)\n'
 'class Container:\n'
 ' def mrz_extraction(self): pass',
 'from custom import mrz_extraction as op\n'
 'op(doc)\n'
 'x.mrz_extraction(doc)\n'
 'class mrz_extraction: pass',
 'import passporteye\npassporteye.read_mrz(doc)\ndef read_mrz(): pass',
 'import passporteye\npassporteye.read_mrz(doc)\nclass Container:\n def read_mrz(self): pass',
 'import passporteye\npassporteye.read_mrz(doc)\nclass read_mrz: pass',
 'import boto3\nx.analyze_id()\ndef analyze_id(): pass',
 'import boto3\nx.analyze_id()\nclass Container:\n def analyze_id(self): pass',
 'import boto3\nx.analyze_id()\nclass analyze_id: pass',
 'import mindee\nmindee.Client()\nx.parse(PassportV1)\ndef parse(): pass',
 'import mindee\n'
 'mindee.Client()\n'
 'x.parse(PassportV1)\n'
 'class Container:\n'
 ' def parse(self): pass',
 'import mindee\nmindee.Client()\nx.parse(PassportV1)\nclass parse: pass',
 'import mindee\nmindee.Client()\nx.parse(PassportV1)\ndef Client(): pass',
 'import mindee\n'
 'mindee.Client()\n'
 'x.parse(PassportV1)\n'
 'class Container:\n'
 ' def Client(self): pass',
 'import mindee\nmindee.Client()\nx.parse(PassportV1)\nclass Client: pass',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument")\n'
 'def DocumentAnalysisClient(): pass',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument")\n'
 'class Container:\n'
 ' def DocumentAnalysisClient(self): pass',
 'from azure.ai.formrecognizer import DocumentAnalysisClient\n'
 'DocumentAnalysisClient()\n'
 'x.begin_analyze_document("prebuilt-idDocument")\n'
 'class DocumentAnalysisClient: pass']

def evidence_case(source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected, source)
    return test

for index, source in enumerate(GOOD_CASES):
    setattr(AuditTests, 'test_evidence_good_%03d' % index, evidence_case(source, True))
for index, source in enumerate(BAD_CASES):
    setattr(AuditTests, 'test_evidence_bad_%03d' % index, evidence_case(source, False))

if __name__ == '__main__':
    unittest.main()
