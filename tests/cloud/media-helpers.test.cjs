const {test}=require('node:test');
const assert=require('node:assert/strict');
const {existsSync}=require('node:fs');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const filename=path.resolve(__dirname,'../../web/src/media-helpers.mjs');
test('video sampling is bounded and excludes invalid or out-of-clip timestamps',async()=>{
  assert.ok(existsSync(filename),'media sampling helper must exist');
  const {sampleTimes}=await import(pathToFileURL(filename));
  assert.deepEqual(sampleTimes(.2),[0]);
  assert.equal(sampleTimes(600).length,120);
  assert.ok(sampleTimes(600).every((v,i,a)=>v>=0&&v<600&&(!i||v>a[i-1])));
  for(const value of [0,-1,NaN,Infinity,601])assert.throws(()=>sampleTimes(value));
});
test('frame statistics export keeps actual per-frame counts and proper CSV quoting',async()=>{
  assert.ok(existsSync(filename),'media CSV helper must exist');
  const {mediaCSV}=await import(pathToFileURL(filename));
  const csv=mediaCSV([{frame_time:5.25,summary:{tables:2,people:3,chairs:4,occupied:1,items_present:1,looks_clear:0,unknown:0}}]);
  assert.match(csv,/5.25,2,3,4,1,1,0,0/);
  assert.equal(csv.trim().split('\n').length,2);
});
