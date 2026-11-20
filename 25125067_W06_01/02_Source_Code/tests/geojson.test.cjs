const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/geojson.js'),'utf8'),context);
const build = (...args) => JSON.parse(JSON.stringify(context.buildGeoJSON(...args)));
const place = {id:'node/1',name:'Synthetic example',lat:10.78,lon:106.7,distance_m:150};

test('GeoJSON uses longitude-latitude order and retains source/license',()=>{
  const result=build([place],{source:'test'},false,'2026-01-01T00:00:00Z');
  assert.equal(result.type,'FeatureCollection');
  assert.deepEqual(result.features[0].geometry.coordinates,[106.7,10.78]);
  assert.equal(result.features[0].id,'node/1');
  assert.equal(result.query.source,'test');
  assert.ok(result.license.includes('odbl'));
});
test('saved places do not claim to come from the current query',()=>{
  const result=build([place],{center:{lat:0,lon:0}},true);
  assert.equal(result.query,null);
  assert.equal(result.features[0].properties.distance_reference,'Original search center at time of saving');
});
test('empty filtered results produce an empty collection and do not mutate inputs',()=>{
  assert.deepEqual(build([],null).features,[]);
  build([place],null);
  assert.equal(place.distance_reference,undefined);
});
