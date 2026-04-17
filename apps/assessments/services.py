import magic
from django.core.exceptions import ValidationError

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

_PDF_MIMES = {'application/pdf'}
_PRESENTATION_MIMES = {
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}
_OTHER_MIMES = _PDF_MIMES | _PRESENTATION_MIMES | {
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/jpeg',
    'image/png',
    'image/gif',
    'text/plain',
}

ALLOWED_MIMES_BY_TYPE = {
    'PDF': _PDF_MIMES,
    'PRESENTATION': _PRESENTATION_MIMES,
    'OTHER': _OTHER_MIMES,
}


def validate_resource_file(file, resource_type: str) -> None:
    """Validate uploaded file size and MIME type. Raises ValidationError on failure."""
    if file.size > MAX_FILE_SIZE:
        raise ValidationError('File size exceeds the 50 MB limit.')

    chunk = file.read(2048)
    file.seek(0)
    detected_mime = magic.from_buffer(chunk, mime=True)

    allowed = ALLOWED_MIMES_BY_TYPE.get(resource_type, _OTHER_MIMES)
    if detected_mime not in allowed:
        raise ValidationError(
            f'Unsupported file type "{detected_mime}" for resource type {resource_type}. '
            f'Allowed: {sorted(allowed)}.'
        )
