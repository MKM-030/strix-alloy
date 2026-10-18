"""PP-local copy of the frozen Halogen loopback transport helpers.

Provenance: scripts/gufo_control/reddit_halogen_client.py, copied without its
historical benchmark controller imports. Only stdlib dependencies are used.
"""
import http.client
import json
import socket
import time

RESPONSE_LIMIT = 1 << 20


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def exchange(method, path, payload=None, timeout=15):
    connection = http.client.HTTPConnection('127.0.0.1', 8731, timeout=timeout)
    began = time.monotonic()
    deadline = began + timeout
    try:
        connection.request(method, path, body=payload,
                           headers={'Content-Type': 'application/json'} if payload is not None else {})
        response = connection.getresponse()
        reader_socket = getattr(getattr(response.fp, 'raw', None), '_sock', None) or connection.sock
        if reader_socket is None:
            raise ValueError('response_socket_unavailable')
        chunks = []
        count = 0
        while not response.isclosed():
            left = deadline-time.monotonic()
            if left <= 0:
                raise TimeoutError('request_deadline')
            # Buffered HTTP readers cannot be reused after a socket timeout.
            # Wait only to the existing absolute deadline; the independent host
            # guard keeps sampling and can stop the owned container meanwhile.
            reader_socket.settimeout(left)
            try:
                part = response.read1(min(65536, RESPONSE_LIMIT+1-count))
            except socket.timeout as error:
                raise TimeoutError('request_deadline') from error
            if not part:
                break
            count += len(part)
            if count > RESPONSE_LIMIT:
                raise ValueError('response_body_limit')
            chunks.append(part)
        raw = b''.join(chunks)
        ended = time.monotonic()
        if len(raw) > RESPONSE_LIMIT:
            raise ValueError('response_body_limit')
        return response.status, dict(response.getheaders()), raw, began, ended
    finally:
        connection.close()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise ValueError('duplicate_json_key')
            value[key] = entry
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
