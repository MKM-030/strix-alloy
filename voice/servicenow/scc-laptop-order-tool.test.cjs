'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'scc-laptop-order-tool.js'), 'utf8');
const ITEM = '401b878b93738354e7f2b9fa6aba102f';
const manager = {toString: () => 'requester-id', getDisplayValue: () => 'Demo Manager'};
const input = {confirmed:'true', employee_name:'Example Employee', start_date:'2026-11-01', delivery_location:'Hamburg', manager_name:''};

function run({reused = false, confirmed = 'true', itemName = 'Actual catalog display from RITM', missingRitm = false} = {}) {
  const calls = {cart:0, add:[], submit:[], queries:[], errors:[]};
  const row = {sys_id:'ritm-id', number:'RITM-FIXTURE', request:'request-id', cat_item:ITEM,
    cat_item_display:itemName, variables:{employee_name:input.employee_name,
      start_date:input.start_date, delivery_location:input.delivery_location, manager}};
  let requestedItemRecords = 0;
  function Record(table, rows = []) {
    this.table = table; this.rows = rows; this.index = -1;
    this.addQuery = (...args) => calls.queries.push([table,...args]);
    this.orderByDesc = () => {}; this.setLimit = () => {}; this.query = () => {};
    this.next = () => { this.index++; if (this.index >= this.rows.length) return false;
      this.current = this.rows[this.index]; this.variables = this.current.variables;
      this.request = {getDisplayValue: () => 'REQ-FIXTURE'}; return true; };
    this.getUniqueValue = () => this.current.sys_id;
    this.getValue = field => String(this.current[field] || '');
    this.getDisplayValue = field => field === 'cat_item' ? this.current.cat_item_display : this.current.name;
    this.get = id => {
      if (table === 'sys_user') this.current={sys_id:id, user_name:'demo-user', name:'Demo Manager'};
      else if (table === 'sc_cat_item' && id === ITEM) this.current={sys_id:ITEM, active:'1', name:'Different master-record display'};
      else return false;
      return true;
    };
  }
  function SecureRecord(table) {
    if (table === 'sc_req_item') return new Record(table, requestedItemRecords++ === 0 ? (reused ? [row] : []) : (missingRitm ? [] : [row]));
    return new Record(table);
  }
  function Cart() {
    calls.cart++;
    this.addToCart = value => calls.add.push(value);
    this.getCartItems = () => new Record('cart', [{cat_item:ITEM, quantity:'1'}]);
    this.submitOrder = value => { calls.submit.push(value); return {request_id:'request-id',request_number:'REQ-FIXTURE'}; };
  }
  const result = vm.runInNewContext(source, {
    inputs:{...input,confirmed}, GlideRecordSecure:SecureRecord,
    GlideDate:function(){this.setValue=value=>{this.value=value;};this.getValue=()=>this.value;},
    gs:{getUserID:()=> 'requester-id',hoursAgoStart:()=> '24h-ago',generateGUID:()=> 'fixture-guid',error:value=>calls.errors.push(value)},
    sn_sc:{CartJS:Cart}
  });
  return {result,calls};
}

test('new order returns the actual RITM catalog identity and places exactly one confirmed order', () => {
  const {result,calls} = run({itemName:'Catalog name from new RITM'});
  assert.equal(result.ok,true); assert.equal(result.reused,false);
  assert.equal(result.catalog_item_id,ITEM);
  assert.equal(result.catalog_item_name,'Catalog name from new RITM');
  assert.equal(result.request_number,'REQ-FIXTURE');
  assert.equal(result.requested_item_number,'RITM-FIXTURE');
  assert.equal(result.employee_name,input.employee_name);
  assert.equal(result.demo_only,true);
  assert.equal(calls.cart,1); assert.equal(calls.add.length,1); assert.equal(calls.submit.length,1);
  assert.equal(calls.add[0].sysparm_id,ITEM); assert.equal(calls.add[0].sysparm_quantity,'1');
  assert.deepEqual(JSON.parse(JSON.stringify(calls.add[0].variables)),{
    employee_name:input.employee_name,start_date:input.start_date,manager:'requester-id',delivery_location:input.delivery_location});
});

test('reuse returns the existing RITM catalog identity without creating or submitting a cart', () => {
  const {result,calls} = run({reused:true,itemName:'Catalog name from reused RITM'});
  assert.equal(result.ok,true); assert.equal(result.reused,true);
  assert.equal(result.catalog_item_id,ITEM);
  assert.equal(result.catalog_item_name,'Catalog name from reused RITM');
  assert.equal(result.request_number,'REQ-FIXTURE'); assert.equal(result.requested_item_number,'RITM-FIXTURE');
  assert.equal(calls.cart,0); assert.equal(calls.add.length,0); assert.equal(calls.submit.length,0);
  assert.ok(calls.queries.some(q=>q[0]==='sc_req_item' && q[1]==='cat_item' && q[2]===ITEM));
});

test('missing explicit confirmation still prevents any order operation', () => {
  for (const confirmed of ['', 'false', 'yes']) {
    const {result,calls} = run({confirmed});
    assert.equal(result.ok,false); assert.equal(result.retry_automatically,false);
    assert.equal(calls.cart,0); assert.equal(calls.submit.length,0);
    assert.equal(result.catalog_item_name,undefined);
  }
});

test('uncertain missing RITM result remains an error and never retries the order', () => {
  const {result,calls} = run({missingRitm:true});
  assert.equal(result.ok,false); assert.equal(result.retry_automatically,false);
  assert.equal(calls.submit.length,1); assert.equal(result.catalog_item_name,undefined);
});
