/*
 * ES5 global Script Include; client callable: false.
 * Model request transformation: new SCCVisionRequestTransformer().build(x_request)
 * Supports direct JSON request bodies and provider wrappers {body: ..., headers: ...}.
 * Attachment IDs use current-user ACL checks. Inline image bytes have already been
 * read by the authorized caller; accepting them never reads a record or external URL.
 */
var SCCVisionRequestTransformer = (function () {
    'use strict';
    var maximumBytes = 5 * 1024 * 1024;
    var own = Object.prototype.hasOwnProperty;

    function fail(reason) {
        throw new Error('SCC Vision: ' + reason);
    }

    function object(value) {
        return value !== null && Object.prototype.toString.call(value) === '[object Object]';
    }

    function trim(value) {
        return value.replace(/^\s+|\s+$/g, '');
    }

    function value(record, name) {
        var result = record.getValue(name);
        return result === null || typeof result === 'undefined' ? '' : String(result);
    }

    function readRecord(table, id, failure) {
        var record = new GlideRecordSecure(table);
        if (!/^[a-f0-9]{32}$/i.test(id) || !record.get(id) || !record.canRead()) {
            fail(failure);
        }
        return record;
    }

    function authorized(parent, caller) {
        var requestId;
        var request;
        if (gs.hasRole('admin') || value(parent, 'opened_by') === caller) {
            return true;
        }
        if (parent.isValidField('requested_for') && value(parent, 'requested_for') === caller) {
            return true;
        }
        if (parent.isValidField('request')) {
            requestId = value(parent, 'request');
            if (/^[a-f0-9]{32}$/i.test(requestId)) {
                request = new GlideRecordSecure('sc_request');
                if (request.get(requestId) && request.canRead() &&
                        request.isValidField('requested_for') && value(request, 'requested_for') === caller) {
                    return true;
                }
            }
        }
        return false;
    }

    function loadImage(attachmentId) {
        var attachment;
        var parent;
        var catalogItem;
        var sizeText;
        var size;
        var mime;
        var caller;
        var bytes;
        var encoded;
        attachment = readRecord('sys_attachment', attachmentId, 'Attachment is unavailable or unreadable.');
        if (value(attachment, 'table_name') !== 'sc_req_item') {
            fail('Attachment must belong to an intake requested item.');
        }
        sizeText = value(attachment, 'size_bytes');
        size = Number(sizeText);
        if (!/^\d+$/.test(sizeText) || !isFinite(size) || size <= 0 || size > maximumBytes) {
            fail('Attachment must contain between 1 byte and 5 MiB.');
        }
        mime = value(attachment, 'content_type');
        if (mime !== 'image/png' && mime !== 'image/jpeg') {
            fail('Attachment must be a PNG or JPEG photo.');
        }
        parent = readRecord('sc_req_item', value(attachment, 'table_sys_id'),
            'Attachment parent is unavailable or unreadable.');
        catalogItem = String(gs.getProperty('scc.form.intake_catalog_item') || '');
        if (!/^[a-f0-9]{32}$/i.test(catalogItem) || value(parent, 'cat_item') !== catalogItem) {
            fail('Attachment does not belong to the configured intake catalog item.');
        }
        caller = String(gs.getUserID() || '');
        if (caller === '' || !authorized(parent, caller)) {
            fail('Caller is not an authorized requester for this intake.');
        }
        try {
            bytes = new GlideSysAttachment().getBytes(attachment);
        } catch (error) {
            fail('Attachment bytes could not be read.');
        }
        if (!bytes || typeof bytes.length !== 'number' || bytes.length <= 0 ||
                bytes.length > maximumBytes || bytes.length !== size) {
            fail('Attachment bytes are empty, oversized or incomplete.');
        }
        try {
            encoded = GlideStringUtil.base64Encode(bytes);
        } catch (encodingError) {
            fail('Attachment bytes could not be encoded.');
        }
        if (encoded === null || typeof encoded === 'undefined') {
            fail('Attachment encoding is empty.');
        }
        encoded = String(encoded);
        if (encoded === '' || encoded.length !== Math.ceil(bytes.length / 3) * 4 ||
                encoded.length > Math.ceil(maximumBytes / 3) * 4 ||
                !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) {
            fail('Attachment encoding is invalid or incomplete.');
        }
        return 'data:' + mime + ';base64,' + encoded;
    }

    function loadInlineImage(source) {
        var original;
        var originalBytes;
        var mime;
        var encoded;
        var padding;
        var size;
        var alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
        var last;
        var head = [];
        var expectedPng = [137, 80, 78, 71, 13, 10, 26, 10];
        var i;
        var a;
        var b;
        var c;
        var d;
        // Bound the encoded input before any scan. Decoded size is checked separately.
        if (source.length > 24 + 23 + Math.ceil(maximumBytes / 3) * 4) {
            fail('Inline image exceeds the 5 MiB limit.');
        }
        // The authorized producer's byte count survives template interpolation and catches
        // truncation by complete Base64 quartets even when the closing marker is restored.
        original = /^SCC_IMAGE_BYTES:([1-9][0-9]{0,6}):/.exec(source);
        if (!original) fail('Inline image must include its original byte count.');
        originalBytes = Number(original[1]);
        if (originalBytes > maximumBytes) fail('Inline image exceeds the 5 MiB limit.');
        source = source.slice(original[0].length);
        if (source.indexOf('data:image/png;base64,') === 0) {
            mime = 'image/png';
            encoded = source.slice(22);
        } else if (source.indexOf('data:image/jpeg;base64,') === 0) {
            mime = 'image/jpeg';
            encoded = source.slice(23);
        } else {
            fail('Inline image must be an exact PNG or JPEG base64 data URI.');
        }
        if (!encoded || encoded.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) {
            fail('Inline image base64 is malformed.');
        }
        padding = encoded.slice(-2) === '==' ? 2 : (encoded.slice(-1) === '=' ? 1 : 0);
        size = encoded.length / 4 * 3 - padding;
        if (size <= 0 || size > maximumBytes) fail('Inline image must contain between 1 byte and 5 MiB.');
        if (size !== originalBytes) fail('Inline image original byte count does not match encoded data.');
        // Reject nonzero unused padding bits: those are alternate encodings of the same bytes.
        if (padding) {
            last = alphabet.indexOf(encoded.charAt(encoded.length - padding - 1));
            if (last < 0 || (padding === 2 && (last & 15) !== 0) || (padding === 1 && (last & 3) !== 0)) {
                fail('Inline image base64 is noncanonical.');
            }
        }
        // Decode only the signature. The complete alphabet, padding and byte count are validated above.
        for (i = 0; i < encoded.length && head.length < 8; i += 4) {
            a = alphabet.indexOf(encoded.charAt(i));
            b = alphabet.indexOf(encoded.charAt(i + 1));
            c = alphabet.indexOf(encoded.charAt(i + 2));
            d = alphabet.indexOf(encoded.charAt(i + 3));
            head.push((a << 2) | (b >> 4));
            if (c >= 0 && head.length < 8) head.push(((b & 15) << 4) | (c >> 2));
            if (d >= 0 && head.length < 8) head.push(((c & 3) << 6) | d);
        }
        if (mime === 'image/png') {
            if (size < 8) fail('Inline PNG signature is incomplete.');
            for (i = 0; i < expectedPng.length; i += 1) {
                if (head[i] !== expectedPng[i]) fail('Inline image MIME and signature differ.');
            }
        } else if (size < 3 || head[0] !== 255 || head[1] !== 216 || head[2] !== 255) {
            fail('Inline image MIME and signature differ.');
        }
        return source;
    }

    function Transformer() {}

    Transformer.prototype.build = function (x_request) {
        var envelope;
        var body;
        var messages;
        var message;
        var markerPattern;
        var prefixes;
        var match;
        var localCount;
        var totalCount = 0;
        var markedIndex = -1;
        var attachmentId;
        var prompt;
        var imageUrl;
        var contentForUrlChecks;
        var i;
        if (typeof x_request !== 'string' || trim(x_request) === '') {
            fail('Request must be a JSON string.');
        }
        try {
            envelope = JSON.parse(x_request, function (key, entry) {
                if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
                    fail('Unsafe request key.');
                }
                return entry;
            });
        } catch (error) {
            fail('Request contains malformed or unsafe JSON.');
        }
        if (!object(envelope)) {
            fail('Request must contain an object.');
        }
        body = own.call(envelope, 'body') ? envelope.body : envelope;
        if (!object(body) || !Array.isArray(body.messages) || body.messages.length === 0) {
            fail('Request must contain a nonempty messages array.');
        }
        messages = body.messages;
        for (i = 0; i < messages.length; i += 1) {
            message = messages[i];
            if (!object(message) || ['system', 'user', 'assistant'].indexOf(message.role) === -1 ||
                    typeof message.content !== 'string') {
                fail('Messages must contain plain text with a supported role.');
            }
            contentForUrlChecks = message.content;
            markerPattern = /\[SCC_ATTACHMENT_ID:([^\]]*)\]/g;
            prefixes = message.content.match(/\[SCC_ATTACHMENT_ID:/g) || [];
            localCount = 0;
            while ((match = markerPattern.exec(message.content)) !== null) {
                localCount += 1;
                totalCount += 1;
                if (message.role !== 'user' || (!/^[a-f0-9]{32}$/i.test(match[1]) && match[1].indexOf('SCC_IMAGE_BYTES:') !== 0) ||
                        trim(message.content.slice(match.index + match[0].length)) !== '') {
                    fail('Attachment marker must end a user message and contain a 32-character sys_id.');
                }
                markedIndex = i;
                attachmentId = match[1];
                prompt = trim(message.content.slice(0, match.index));
                contentForUrlChecks = prompt;
            }
            if (prefixes.length !== localCount) {
                fail('Attachment marker is malformed.');
            }
            if (/https?:\/\/|data\s*:/i.test(contentForUrlChecks)) {
                fail('External URLs and existing image data are not accepted.');
            }
        }
        if (totalCount !== 1 || markedIndex < 0 || prompt === '') {
            fail('Exactly one attachment marker and a nonempty extraction prompt are required.');
        }
        imageUrl = /^[a-f0-9]{32}$/i.test(attachmentId) ? loadImage(attachmentId) : loadInlineImage(attachmentId);
        messages[markedIndex].content = [
            {type: 'text', text: prompt},
            {type: 'image_url', image_url: {url: imageUrl}}
        ];
        body.model = 'halogen-v2';
        body.temperature = 0;
        body.stream = false;
        body.max_tokens = 3072;
        delete body.response_format;
        return envelope;
    };

    return Transformer;
}());

if (typeof module !== 'undefined' && module.exports) {
    module.exports = SCCVisionRequestTransformer;
}
