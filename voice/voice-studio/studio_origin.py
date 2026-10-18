"""Explicit operator-selected HTTPS origin shared by Studio launch and HTTP guards."""
import os
import re


def validated_origin(value):
    error = 'Set --origin or SCC_VOICE_STUDIO_ORIGIN to one exact HTTPS origin'
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(error)
    match = re.fullmatch(r'https://([A-Za-z0-9.-]+)(?::([1-9][0-9]{0,4}))?/?', value)
    if not match:
        raise ValueError(error)
    host, port = match.groups()
    labels = host.split('.')
    if len(host) > 253 or any(not re.fullmatch(
            r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in labels):
        raise ValueError(error)
    if port and int(port) > 65535:
        raise ValueError(error)
    if re.fullmatch(r'(?:[0-9]+|0x[0-9a-f]*)', labels[-1], re.IGNORECASE):
        if len(labels) != 4 or any(not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', label)
                                  or int(label) > 255 for label in labels):
            raise ValueError(error)
    return 'https://' + host.lower() + ((':' + port) if port and port != '443' else '')


def configured_origin(value=None):
    return validated_origin(os.environ.get('SCC_VOICE_STUDIO_ORIGIN') if value is None else value)
