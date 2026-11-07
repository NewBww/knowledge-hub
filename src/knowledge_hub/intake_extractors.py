"""Bounded, non-executing extractors. Failures retain originals without invented text."""
from pathlib import PurePosixPath
from .core import DomainError

TEXT_TYPES = {'text/plain', 'text/markdown', 'text/csv', 'application/json'}
MAX_TEXT = 100000


def safe_name(name):
    if ('\\' in name or ':' in name or any(ord(c) < 32 for c in name)
            or name.startswith('/') or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise DomainError('unsafe_upload_name', 422)
    return str(PurePosixPath(name))


def _extract(data, media_type):
    if media_type in {'image/png', 'image/jpeg', 'image/webp'}:
        from io import BytesIO
        import warnings
        from PIL import Image
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.width * image.height > 20000000 or getattr(image, 'n_frames', 1) != 1:
                        return {'status': 'unprocessed', 'reason': 'image_limit', 'text': ''}
                    if image.format != {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}[media_type]:
                        return {'status': 'unprocessed', 'reason': 'image_type_mismatch', 'text': ''}
                    image.verify()
                    return {'status': 'image', 'text': '', 'width': image.width, 'height': image.height}
        except Exception:
            return {'status': 'unprocessed', 'reason': 'invalid_image', 'text': ''}
    if media_type in TEXT_TYPES:
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            return {'status': 'unprocessed', 'reason': 'invalid_utf8', 'text': ''}
        if len(text) > MAX_TEXT:
            return {'status': 'unprocessed', 'reason': 'extracted_text_limit', 'text': ''}
        return {'status': 'extracted', 'text': text}
    if media_type in {'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}:
        from io import BytesIO
        import zipfile
        import logging
        try:
            if media_type == 'application/pdf':
                from pypdf import PdfReader, filters
                for limit in ('FLATE_MAX_BUFFER_SIZE', 'JBIG2_MAX_OUTPUT_LENGTH', 'LZW_MAX_OUTPUT_LENGTH', 'MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH', 'MAX_DECLARED_STREAM_LENGTH', 'RUN_LENGTH_MAX_OUTPUT_LENGTH', 'ZLIB_MAX_OUTPUT_LENGTH'):
                    setattr(filters, limit, 4 * 1024 * 1024)
                # Do not emit document-derived parser diagnostics into application logs.
                logger = logging.getLogger('pypdf')
                old_level = logger.level
                logger.setLevel(logging.CRITICAL)
                try:
                    pdf = PdfReader(BytesIO(data), strict=True)
                    if pdf.is_encrypted:
                        return {'status': 'unprocessed', 'reason': 'password_protected', 'text': ''}
                    if len(pdf.pages) > 100:
                        return {'status': 'unprocessed', 'reason': 'document_limit', 'text': ''}
                    chunks = []
                    for page in pdf.pages:
                        content = page.get_contents()
                        if content is not None and len(content.get_data()) > 2 * 1024 * 1024:
                            return {'status': 'unprocessed', 'reason': 'document_limit', 'text': ''}
                        chunks.append(page.extract_text() or '')
                        if sum(map(len, chunks)) > MAX_TEXT:
                            return {'status': 'unprocessed', 'reason': 'extracted_text_limit', 'text': ''}
                    text = '\n'.join(chunks)
                finally:
                    logger.setLevel(old_level)
            else:
                # Bound expansion before python-docx/lxml sees the ZIP container.
                if data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
                    return {'status': 'unprocessed', 'reason': 'password_protected_or_legacy_office', 'text': ''}
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    entries = archive.infolist()
                    if any(entry.flag_bits & 1 for entry in entries):
                        return {'status': 'unprocessed', 'reason': 'password_protected', 'text': ''}
                    if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024:
                        return {'status': 'unprocessed', 'reason': 'document_limit', 'text': ''}
                from docx import Document
                doc = Document(BytesIO(data))
                text = '\n'.join([paragraph.text for paragraph in doc.paragraphs] +
                                 [cell.text for table in doc.tables for row in table.rows for cell in row.cells])
            if len(text) > MAX_TEXT:
                return {'status': 'unprocessed', 'reason': 'extracted_text_limit', 'text': ''}
            if not text.strip():
                return {'status': 'unprocessed', 'reason': 'no_extractable_text', 'text': ''}
            return {'status': 'extracted', 'text': text}
        except Exception:
            return {'status': 'unprocessed', 'reason': 'invalid_document', 'text': ''}
    return {'status': 'unprocessed', 'reason': 'unsupported_media_type', 'text': ''}


def extract(data, media_type):
    if media_type not in {'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}:
        return _extract(data, media_type)
    import json
    import subprocess
    import sys
    # Fixed executable/arguments only; no upload-derived command, shell or path.
    args = ([sys.executable, '--capture-extractor-worker', media_type] if getattr(sys, 'frozen', False)
            else [sys.executable, '-m', 'knowledge_hub.intake_extractors', '--worker', media_type])
    try:
        result = subprocess.run(args, input=data, capture_output=True, timeout=6, env={})
        if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
            return {'status': 'unprocessed', 'reason': 'extraction_worker_failed', 'text': ''}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {'status': 'unprocessed', 'reason': 'extraction_timeout', 'text': ''}
    except (OSError, ValueError):
        return {'status': 'unprocessed', 'reason': 'extraction_unavailable', 'text': ''}


def worker_main(media_type):
    """Frozen CLI must dispatch its private worker flag here before startup."""
    import json
    import resource
    import sys
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
        if sys.platform != 'darwin':
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        data = sys.stdin.buffer.read(5 * 1024 * 1024 + 1)
        result = (_extract(data, media_type) if len(data) <= 5 * 1024 * 1024
                  else {'status': 'unprocessed', 'reason': 'document_limit', 'text': ''})
    except Exception:
        result = {'status': 'unprocessed', 'reason': 'extraction_unavailable', 'text': ''}
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker_main(sys.argv[2])
