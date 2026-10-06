import test from 'node:test'; import assert from 'node:assert/strict'; import {tetherlessGroup} from '../src/tetherless-identity.js';
test('preserves Release Tetherless main and both extension IDs',()=>{const root='org.tetherless.Tetherless';assert.equal(tetherlessGroup([root,root+'.AltWidget',root+'.SideBackup'].map(id=>({id}))).identifier,'group.'+root);});
test('preserves existing Debug suffix without appending another Team',()=>{const root='org.tetherless.Tetherless.ABC1234567';assert.equal(tetherlessGroup([{id:root},{id:root+'.AltWidget'}]).identifier,'group.'+root);});
test('does not grant arbitrary third-party apps Tetherless capabilities',()=>assert.equal(tetherlessGroup([{id:'org.example.App'}]),null));
test('rejects unexpected nested bundles in recognized manager',()=>assert.throws(()=>tetherlessGroup([{id:'org.tetherless.Tetherless'},{id:'org.unexpected.Extension'}]),/unrecognized/));
