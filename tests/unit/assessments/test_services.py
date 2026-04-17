import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError

from apps.assessments.services import MAX_FILE_SIZE, validate_resource_file


def _make_file(content=b'data', size=None):
    f = MagicMock()
    f.read = lambda n=-1: content[:n] if n >= 0 else content
    f.seek = MagicMock()
    f.size = size if size is not None else len(content)
    return f


# ---------------------------------------------------------------------------
# File size validation
# ---------------------------------------------------------------------------

class TestFileSizeValidation:
    def test_file_exactly_at_limit_is_accepted(self):
        f = _make_file(size=MAX_FILE_SIZE)
        with patch('apps.assessments.services.magic.from_buffer', return_value='application/pdf'):
            validate_resource_file(f, 'PDF')  # should not raise

    def test_file_over_limit_raises(self):
        f = _make_file(size=MAX_FILE_SIZE + 1)
        with pytest.raises(ValidationError, match='50 MB'):
            validate_resource_file(f, 'PDF')

    def test_file_well_over_limit_raises(self):
        f = _make_file(size=100 * 1024 * 1024)
        with pytest.raises(ValidationError, match='50 MB'):
            validate_resource_file(f, 'PDF')


# ---------------------------------------------------------------------------
# MIME type validation
# ---------------------------------------------------------------------------

class TestMimeTypeValidation:
    @patch('apps.assessments.services.magic.from_buffer', return_value='application/pdf')
    def test_valid_pdf_mime_accepted(self, _mock):
        f = _make_file()
        validate_resource_file(f, 'PDF')  # no raise

    @patch('apps.assessments.services.magic.from_buffer', return_value='text/plain')
    def test_text_file_as_pdf_rejected(self, _mock):
        f = _make_file()
        with pytest.raises(ValidationError, match='text/plain'):
            validate_resource_file(f, 'PDF')

    @patch(
        'apps.assessments.services.magic.from_buffer',
        return_value='application/vnd.openxmlformats-officedocument.presentationml.presentation',
    )
    def test_valid_presentation_mime_accepted(self, _mock):
        f = _make_file()
        validate_resource_file(f, 'PRESENTATION')  # no raise

    @patch('apps.assessments.services.magic.from_buffer', return_value='application/pdf')
    def test_pdf_as_presentation_rejected(self, _mock):
        f = _make_file()
        with pytest.raises(ValidationError, match='application/pdf'):
            validate_resource_file(f, 'PRESENTATION')

    @patch('apps.assessments.services.magic.from_buffer', return_value='text/plain')
    def test_text_file_accepted_as_other(self, _mock):
        f = _make_file()
        validate_resource_file(f, 'OTHER')  # text/plain is in OTHER's allowed set

    @patch('apps.assessments.services.magic.from_buffer', return_value='application/x-executable')
    def test_executable_rejected_for_other(self, _mock):
        f = _make_file()
        with pytest.raises(ValidationError):
            validate_resource_file(f, 'OTHER')

    @patch('apps.assessments.services.magic.from_buffer', return_value='text/plain')
    def test_seek_is_called_after_read(self, _mock):
        f = _make_file()
        validate_resource_file(f, 'OTHER')
        f.seek.assert_called_once_with(0)
