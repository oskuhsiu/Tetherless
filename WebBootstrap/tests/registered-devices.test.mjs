import test from 'node:test'; import assert from 'node:assert/strict';
import { validateDevices } from '../src/registered-devices.js';
const device={udid:'00000000-0000000000000000',name:'Registered phone',status:'active',selectable:true};
test('registered devices: exact Team, bounded list and safe normalized backend fields',()=>{
  assert.deepEqual(validateDevices({teamId:'TEAM',devices:[device]},'TEAM'),[device]);
  for(const body of [{teamId:'OTHER',devices:[device]},{teamId:'TEAM',devices:Array(1001).fill(device)},{teamId:'TEAM',devices:[device,device]},{teamId:'TEAM',devices:[{...device,udid:'invalid'}]},{teamId:'TEAM',devices:[{...device,name:'bad\nname'}]},{teamId:'TEAM',devices:[{...device,name:'x'.repeat(129)}]}])assert.throws(()=>validateDevices(body,'TEAM'));
});
test('registered devices: disabled or unknown status is never selectable, even if a flag claims otherwise',()=>{
  for(const status of ['disabled','unknown'])assert.equal(validateDevices({teamId:'TEAM',devices:[{...device,status,selectable:true}]},'TEAM')[0].selectable,false);
});
