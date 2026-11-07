'use strict';

// CPU-only characterization of the existing own note protocol. No native APIs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function protocol() {
    const context = {Class: {create: () => function CallerContext() {}}};
    vm.runInNewContext(fs.readFileSync(
        path.join(__dirname, 'SCCVoiceCallerContext.v1.candidate.js'), 'utf8'), context);
    return new context.SCCVoiceCallerContext();
}

function row(helper, id, revision, text) {
    const message = helper.noteText(id.repeat(32), revision, text);
    return {message, user_message: message};
}

test('native helper accepts a later cumulative note with the exact previous prefix', () => {
    const helper = protocol();
    const notes = helper.orderedNotes([
        row(helper, 'a', 1, 'Lieferort Berlin.'),
        row(helper, 'b', 2, 'Lieferort Berlin.\nEintritt am ersten Dezember.')
    ]);
    assert.equal(notes.length, 2);
    assert.equal(notes[1].text, 'Lieferort Berlin.\nEintritt am ersten Dezember.');
});

test('resetting only Bridge would still leave a conflicting native note chain', () => {
    const helper = protocol();
    assert.throws(() => helper.orderedNotes([
        row(helper, 'a', 1, 'Lieferort Berlin.'),
        row(helper, 'b', 2, 'Eintritt am ersten Dezember.')
    ]), error => error.sccCode === 'context_note_ambiguous');
});
