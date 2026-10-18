#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const app = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('deletion controls require explicit server permission, even for an apparent owner', () => {
  assert.equal(typeof app.deletionAvailability, 'function', 'deletion policy is available');
  assert.equal(app.deletionAvailability({id:'own', owner_is_self:true}, 'other'), 'hidden');
  assert.equal(app.deletionAvailability({id:'own', owner_is_self:true, can_delete:false}, 'other'), 'hidden');
  assert.equal(app.deletionAvailability({id:'shared', owner_is_self:false, can_delete:true}, 'other'), 'allowed');
});

test('the selected voice must be changed before its deletion control can be used', () => {
  assert.equal(typeof app.deletionAvailability, 'function', 'deletion policy is available');
  const profile = {id:'own', can_delete:true};
  assert.equal(app.deletionAvailability(profile, 'own'), 'selected');
  assert.equal(app.deletionAvailability(profile, 'other'), 'allowed');
});

test('the packaged standard voice never exposes a deletion control', () => {
  assert.equal(typeof app.deletionAvailability, 'function', 'deletion policy is available');
  assert.equal(app.deletionAvailability({id:'synthetic-scc-demo', can_delete:true}, 'own'), 'hidden');
});
