"""Private extractor dispatch must not start the desktop app or create user data."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from docx import Document


def test_cli_private_docx_worker_extracts_without_starting_app(tmp_path):
    document = Document()
    document.add_paragraph('Synthetic worker text; no private knowledge.')
    data = io.BytesIO()
    document.save(data)
    user_data = tmp_path / 'must-not-be-initialized'
    result = subprocess.run(
        [sys.executable, '-m', 'knowledge_hub.cli', '--capture-extractor-worker',
         'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        input=data.getvalue(), capture_output=True, timeout=10,
        env={**os.environ, 'KNOWLEDGE_HUB_DATA_DIR': str(user_data)},
    )
    assert result.returncode == 0, result.stderr.decode()
    payload = json.loads(result.stdout)
    assert payload['status'] == 'extracted'
    assert payload['text'] == 'Synthetic worker text; no private knowledge.'
    assert not user_data.exists()
