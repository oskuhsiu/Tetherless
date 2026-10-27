import test from 'node:test'; import assert from 'node:assert/strict'; import { parse } from '../src/vendor/binary-plist.js';
function arrayFixture(levels, duplicate=true) {const header=Buffer.from('bplist00'),table=[],parts=[];let offset=8;for(let i=0;i<levels;i++){table.push(offset);parts.push(Buffer.from(duplicate?[0xa2,i+1,i+1]:[0xa1,i+1]));offset+=duplicate?3:2;}table.push(offset);parts.push(Buffer.from([0xa0]));offset++;const trailer=Buffer.alloc(32);trailer[6]=1;trailer[7]=1;trailer.writeBigUInt64BE(BigInt(levels+1),8);trailer.writeBigUInt64BE(0n,16);trailer.writeBigUInt64BE(BigInt(offset),24);return Buffer.concat([header,...parts,Buffer.from(table),trailer]);}
function run(bytes){return parse(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));}
test('ordinary small binary plist remains supported',()=>assert.deepEqual(run(arrayFixture(3,false)),[[[[]]]]));
test('bounded valid shared references stop at traversal budget',()=>assert.throws(()=>run(arrayFixture(16)),/traversal budget/));
test('deep ordinary array chain stops at depth budget',()=>assert.throws(()=>run(arrayFixture(35,false)),/traversal budget/));
test('input-byte budget rejects before parsing',()=>assert.throws(()=>parse(new ArrayBuffer(1024*1024+1)),/input budget/));
