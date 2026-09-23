import test from 'node:test';
import assert from 'node:assert/strict';
import {shiftDay,shiftMonth,monthCells,focusRatio,createDemo} from '../src/data.js';
test('date navigation crosses year boundaries without timezone conversion',()=>{
  assert.equal(shiftDay('2026-12-31',1),'2027-01-01');
  assert.equal(shiftDay('2026-01-01',-1),'2025-12-31');
  assert.equal(shiftMonth('2026-12-23',1),'2027-01-23');
});
test('month navigation clamps dates and handles leap years',()=>{
  assert.equal(shiftMonth('2026-01-31',1),'2026-02-28');
  assert.equal(shiftMonth('2028-01-31',1),'2028-02-29');
  assert.equal(monthCells('2028-02-29').filter(Boolean).length,29);
});
test('calendar starts Monday and includes complete rows with no duplicate dates',()=>{
  const cells=monthCells('2026-09-23');assert.equal(cells[0],null);assert.equal(cells[1],'2026-09-01');
  assert.equal(cells.length%7,0);assert.equal(new Set(cells.filter(Boolean)).size,30);
});
test('focus progress distinguishes full, half and no record',()=>{
  assert.equal(focusRatio({total:6,returned:6}),1);
  assert.equal(focusRatio({total:6,returned:3}),.5);
  assert.equal(focusRatio({total:0,returned:0}),0);
  assert.equal(focusRatio(undefined),0);
});
test('demo tasks contain unique actions and no future focus measurements',()=>{
  const data=createDemo('2026-09-23');
  assert.deepEqual(data.focus['2026-09-23'],{total:6,returned:3});
  assert.deepEqual(data.focus['2026-09-22'],{total:6,returned:6});
  assert.ok(Object.keys(data.focus).every(k=>k<='2026-09-23'));
  assert.equal(new Set(data.tasks['2026-09-23'].flatMap(t=>t.steps.map(s=>s.id))).size,5);
});
