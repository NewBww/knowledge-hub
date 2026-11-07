import base64
from pathlib import Path
import pytest
from io import BytesIO
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store


def test_paste_capture_survives_restart_and_is_metadata_only_in_list(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='private synthetic paste'))
    again = Intake(store).get(project, capture['id'])
    assert again['text'] == 'private synthetic paste'
    assert len(again['snapshot_sha256']) == 64
    metadata = Intake(store).list(project)[0]
    assert 'text' not in metadata and 'intent' not in metadata
    assert metadata['id'] == capture['id']
    Intake(store).delete(project, capture['id'])
    with pytest.raises(DomainError, match='capture_not_found'):
        Intake(store).get(project, capture['id'])


def test_folder_upload_is_local_and_traversal_is_rejected(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    intake = Intake(store)
    file = {'name': 'folder/note.txt', 'media_type': 'text/plain', 'content_base64': base64.b64encode(b'actual content').decode()}
    capture = intake.create(project, CaptureInput(files=[file]))
    assert capture['files'][0]['text'] == 'actual content'
    assert capture['files'][0]['status'] == 'extracted'
    assert not (tmp_path / 'captures' / capture['id'] / 'folder').exists()
    for name in ['../outside.txt', '/absolute.txt', 'a\\b.txt', 'a//b.txt', 'a/./b.txt', 'C:/file.txt']:
        file['name'] = name
        with pytest.raises(DomainError, match='unsafe_upload_name'):
            intake.create(project, CaptureInput(files=[file]))


def test_actual_document_extraction_and_explicit_errors():
    from knowledge_hub.intake_extractors import extract
    from docx import Document
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
    doc = Document()
    doc.add_paragraph('Document paragraph')
    doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Table cell'
    content = BytesIO()
    doc.save(content)
    result = extract(content.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert result['status'] == 'extracted'
    assert 'Document paragraph' in result['text'] and 'Table cell' in result['text']
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 100 Td (Actual PDF words) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    content = BytesIO()
    writer.write(content)
    assert 'Actual PDF words' in extract(content.getvalue(), 'application/pdf')['text']
    writer.encrypt('secret')
    encrypted = BytesIO()
    writer.write(encrypted)
    assert extract(encrypted.getvalue(), 'application/pdf')['reason'] == 'password_protected'
    assert extract(b'not a pdf', 'application/pdf')['reason'] == 'invalid_document'
    assert extract(b'anything', 'application/octet-stream')['reason'] == 'unsupported_media_type'
    assert extract(b'\xff', 'text/plain')['reason'] == 'invalid_utf8'


def test_images_are_validated_and_never_claimed_as_ocr():
    from knowledge_hub.intake_extractors import extract
    from PIL import Image
    content = BytesIO()
    Image.new('RGB', (2, 3), 'red').save(content, format='PNG')
    result = extract(content.getvalue(), 'image/png')
    assert result == {'status': 'image', 'text': '', 'width': 2, 'height': 3}
    assert extract(content.getvalue(), 'image/jpeg')['reason'] == 'image_type_mismatch'
    assert extract(b'not an image', 'image/png')['reason'] == 'invalid_image'


def test_pdf_content_stream_is_bounded_before_text_parsing():
    from knowledge_hub.intake_extractors import extract
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b' ' * (2 * 1024 * 1024 + 1))
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    content = BytesIO()
    writer.write(content)
    assert extract(content.getvalue(), 'application/pdf')['reason'] == 'document_limit'


def test_changed_capture_manifest_cannot_reuse_approved_snapshot(tmp_path):
    import json
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='inspected'))
    manifest = tmp_path / 'captures' / capture['id'] / 'capture.json'
    changed = json.loads(manifest.read_text())
    changed['text'] = 'not inspected'
    manifest.write_text(json.dumps(changed))
    with pytest.raises(DomainError, match='capture_integrity_error'):
        Intake(store).get(project, capture['id'])


def test_document_extractor_timeout_is_explicit_and_never_returns_partial_text(monkeypatch):
    import subprocess
    from knowledge_hub.intake_extractors import extract
    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == 6
        assert not kwargs.get('shell', False)
        raise subprocess.TimeoutExpired(args[0], 6)
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert extract(b'%PDF-1.7 synthetic', 'application/pdf') == {'status': 'unprocessed', 'reason': 'extraction_timeout', 'text': ''}


def test_expired_originals_are_purged_when_service_starts(tmp_path):
    import json
    from datetime import datetime, timedelta, timezone
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    payload = Intake(store).create(project, CaptureInput(files=[{'name': 'note.txt', 'media_type': 'text/plain', 'content_base64': 'aGk='}]))
    directory = tmp_path / 'captures' / payload['id']
    payload['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    (directory / 'capture.json').write_text(json.dumps(payload))
    Intake(store)
    assert not directory.exists()
