import test from 'node:test';
import assert from 'node:assert/strict';
import {selectCells,summarize,statusFor} from '../web/model.mjs';
test('filters calendar month, capture lead and local day part independently', () => {
  const rows = [{month:'2026-11',day:1,period:'Morning'}, {month:'2026-12',day:2,period:'Evening'}];
  assert.deepEqual(selectCells(rows,'2026-12','2','Evening'),[rows[1]]);
  assert.deepEqual(selectCells(rows,'','2','Morning'),[]);
});
test('pooled MAE and signed bias weight individual matches; largest change uses magnitude', () => {
  const rows = [{matched:1,eligible:2,sum_error:-3,sum_absolute:3,largest_revision:{change:-4}},
    {matched:2,eligible:3,sum_error:1,sum_absolute:3,largest_revision:{change:3}}];
  assert.deepEqual(summarize(rows),{matched:3,eligible:5,bias:-2/3,mae:2,revision:{change:-4}});
  assert.equal(summarize([]).mae,null);
});
test('zero is measured; flags and future or missing hours stay explicit', () => {
  const valid='2026-11-19T06:00:00Z';
  assert.equal(statusFor(valid,[0,null],valid),'Matched');
  assert.equal(statusFor(valid,[-2,'E'],valid),'Flagged · E');
  assert.equal(statusFor(valid,[null,null],valid),'Awaiting reading');
  assert.equal(statusFor(valid,undefined,'2026-11-19T05:59:00Z'),'Future');
});
