from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            'success': False,
            'message': _extract_message(response.data),
            'data': {},
        }

    return response


def _extract_message(data) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return _extract_message(data[0])
    if isinstance(data, dict):
        for key in ('detail', 'non_field_errors', 'message'):
            if key in data:
                return _extract_message(data[key])
        # Return first field's first error
        for value in data.values():
            return _extract_message(value)
    return 'An error occurred.'
