/* Inactive original-bearer native-session diagnostic. Loading performs no IO.
 * Wire authority: .superpowers/sdd/2026-11-03-native-oauth-boundary-probe/wire-preflight.md.
 * Credentials and metadata transport belong to the private driver, never this module.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SccNativeOAuthSessionProbe = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  var ORIGIN = 'https://soprasteriaassvsdemo14.service-now.com';
  var VENDOR = 'c2f0b8f187033200246ddd4c97cb0bb9', PROFILE = 'c623e20f93374354e7f2b9fa6aba1081';
  var TRANSACTION = 'Interface=Chat,Interface-Type=Unknown,Interface-Name=Unknown,Interface-SysID=0d5bb8b9730303004ab2369f2ef6a737';
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, ID = /^[0-9a-f]{32}$/;
  var ACTIVE = ['open','chatInProgress','autoPilotInProgress'], TERMINAL = ['completed','faulted','canceled','chatEnded','deleted'];
  var ORACLE_KEYS = ['version','phase','attemptId','deviceId','ok','failureCode','principalHash','server','contextUnchanged','counts','conversations','sessions','deviceConversations','deviceSessions','unownedDeviceRows','activity','messageSessionLinks'];
  var CKEYS = ['id','consumerId','accountId','vendorId','profileId','deviceId','state','createdMs','updatedMs','modCount'];
  var SKEYS = ['id','consumerId','accountId','vendorId','deviceId','deviceType','createdMs'];
  function Failure(code) {this.code = code;}
  function fail(code) {throw new Failure(code);}
  function need(value, code) {if (!value) fail(code);}
  function object(value) {return value !== null && typeof value === 'object' && !Array.isArray(value);}
  function has(value, key) {return Object.prototype.hasOwnProperty.call(value, key);}
  function exact(value, keys) {return object(value) && Object.keys(value).length === keys.length && keys.every(function (key) {return has(value,key);});}
  function integer(value, cap) {return Number.isSafeInteger(value) && value >= 0 && value <= cap;}
  function reference(value) {return value === null || typeof value === 'string' && ID.test(value);}
  function same(a,b) {return JSON.stringify(a) === JSON.stringify(b);}
  function freeze(value) {if (value && typeof value === 'object') {Object.keys(value).forEach(function (key) {freeze(value[key]);});Object.freeze(value);}return value;}
  function discard(response) {try {if(response && response.body) Promise.resolve(response.body.cancel()).catch(function () {});} catch (_) {}}
  function cancel(reader) {try {if(reader) Promise.resolve(reader.cancel()).catch(function () {});} catch (_) {}}
  function channel(value) {
    if(typeof value !== 'string' || value.length > 512 || !/^\/?[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*$/.test(value)) return null;
    var parts = value.split('/');
    if(parts.some(function (part) {return part.length > 128;})) return null;
    return parts[parts.length-1];
  }
  // Strict consumer-side validation deliberately repeats the server boundary checks.
  function snapshot(raw, req) {
    var code = 'PRECHECK_REFUSED';
    need(exact(raw,ORACLE_KEYS) && raw.version === 1 && raw.phase === req.phase && raw.attemptId === req.attemptId && raw.deviceId === req.deviceId,code);
    need(raw.ok === true && raw.failureCode === null && raw.contextUnchanged === true && typeof raw.principalHash === 'string' && /^[0-9a-f]{64}$/.test(raw.principalHash),code);
    need(exact(raw.server,['startedMs','finishedMs']) && integer(raw.server.startedMs,Number.MAX_SAFE_INTEGER) && integer(raw.server.finishedMs,Number.MAX_SAFE_INTEGER) && raw.server.finishedMs >= raw.server.startedMs && raw.server.finishedMs-raw.server.startedMs <= 15000,code);
    need(exact(raw.counts,['activeConversations','unknownStates']) && integer(raw.counts.activeConversations,512) && integer(raw.counts.unknownStates,512) && integer(raw.unownedDeviceRows,1024),code);
    function rows(values, conversation) {
      need(Array.isArray(values) && values.length <= 512,code);
      var seen = new Set();
      values.forEach(function (r) {
        need(exact(r,conversation?CKEYS:SKEYS) && typeof r.id === 'string' && ID.test(r.id) && !seen.has(r.id),code);seen.add(r.id);
        need(reference(r.consumerId) && reference(r.accountId) && (r.consumerId !== null || r.accountId !== null) && reference(r.vendorId) && (r.deviceId === null || r.deviceId === req.deviceId) && integer(r.createdMs,Number.MAX_SAFE_INTEGER),code);
        if(conversation) need(reference(r.profileId) && typeof r.state === 'string' && r.state.length <= 128 && integer(r.updatedMs,Number.MAX_SAFE_INTEGER) && r.updatedMs >= r.createdMs && integer(r.modCount,Number.MAX_SAFE_INTEGER),code);
        else need(r.deviceType === null || ['mweb','ios','android','nowassistpanel'].indexOf(r.deviceType) >= 0,code);
      });
    }
    rows(raw.conversations,true);rows(raw.sessions,false);rows(raw.deviceConversations,true);rows(raw.deviceSessions,false);
    function deviceRows(all,device) {
      var expected = all.filter(function (r) {return r.deviceId === req.deviceId;});
      need(device.length === expected.length,code);
      device.forEach(function (r) {need(r.deviceId === req.deviceId && expected.some(function (e) {return same(e,r);}),code);});
    }
    deviceRows(raw.conversations,raw.deviceConversations);deviceRows(raw.sessions,raw.deviceSessions);
    need(raw.counts.activeConversations === raw.conversations.filter(function (r) {return ACTIVE.indexOf(r.state)>=0;}).length && raw.counts.unknownStates === raw.conversations.filter(function (r) {return ACTIVE.indexOf(r.state)<0 && TERMINAL.indexOf(r.state)<0;}).length,code);
    need(exact(raw.activity,['available','messages','plans','genai','tools']) && typeof raw.activity.available === 'boolean',code);
    ['messages','plans','genai','tools'].forEach(function (key) {need(raw.activity.available ? integer(raw.activity[key],512) : raw.activity[key] === null,code);});
    need(Array.isArray(raw.messageSessionLinks) && raw.messageSessionLinks.length<=512 && (raw.activity.available || raw.messageSessionLinks.length === 0),code);
    var links = new Set();
    raw.messageSessionLinks.forEach(function (r) {
      need(exact(r,['conversationId','sessionId']) && typeof r.conversationId === 'string' && ID.test(r.conversationId) && reference(r.sessionId) && raw.deviceConversations.some(function (c) {return c.id === r.conversationId;}),code);
      var key = r.conversationId + ':' + r.sessionId;need(!links.has(key),code);links.add(key);
    });
    if(raw.activity.available) need(raw.messageSessionLinks.length <= raw.activity.messages,code);
    // Clone before storing any proof; callbacks cannot mutate retained baseline rows.
    return freeze(JSON.parse(JSON.stringify(raw)));
  }
  function createNativeOAuthSessionProbe(options) {
    options = options || {};
    var origin = options.origin, fetchNative = options.fetchNative, inspect = options.inspect, callerHash = options.callerHash;
    var uuid = options.uuid || function () {return globalThis.crypto.randomUUID();};
    var now = options.now || function () {return Date.now();};
    var monotonic = options.monotonic || function () {return globalThis.performance.now();};
    var sleep = options.sleep || function (ms) {return new Promise(function (resolve) {setTimeout(resolve,ms);});};
    var once, used = new Set(), previousTick = null;
    function ticks() {var n = monotonic();need(Number.isFinite(n) && n>=0 && (previousTick === null || n>=previousTick),'INVALID_CONFIG');previousTick=n;return n;}
    function stamp() {var n=now();need(integer(n,Number.MAX_SAFE_INTEGER),'INVALID_CONFIG');return n;}
    function newId() {var n=uuid();need(typeof n==='string' && UUID.test(n) && !used.has(n),'INVALID_CONFIG');used.add(n);return n;}
    function failure(e) {return e instanceof Failure ? e.code : 'REQUEST_FAILED';}
    // Every potentially uncooperative promise is raced against a real timer, and
    // its late result is discarded. Cleanup never receives the caller's signal.
    async function bounded(task, ms, signal) {
      need(ms>0,'TIMEOUT');
      var controller=new AbortController(), timer, onAbort, stopped=false;
      var stop=new Promise(function (_,reject) {
        timer=setTimeout(function () {stopped=true;controller.abort();reject(new Failure('TIMEOUT'));},Math.ceil(ms));
        if(signal) {onAbort=function () {stopped=true;controller.abort();reject(new Failure('CANCELLED'));};signal.addEventListener('abort',onAbort,{once:true});if(signal.aborted)onAbort();}
      });
      try {return await Promise.race([stop,Promise.resolve().then(function () {need(!stopped,'CANCELLED');return task(controller.signal,function () {return stopped;});})]);}
      finally {stopped=true;clearTimeout(timer);if(signal && onAbort)signal.removeEventListener('abort',onAbort);controller.abort();}
    }
    async function request(path,method,body,headers,ms,signal,json,status) {
      var reader;
      try {return await bounded(async function (abort,stopped) {
        var response=await fetchNative(origin+path,{method:method,credentials:'omit',redirect:'error',headers:Object.assign({Accept:'application/json','Content-Type':'application/json','X-Transaction-Source':TRANSACTION},headers),body:body===undefined?undefined:JSON.stringify(body),signal:abort});
        if(stopped()){discard(response);fail('TIMEOUT');}
        if(response && integer(response.status,599) && response.status>=100)status(response.status);
        try {
          need(response && !response.redirected && (!response.url || new URL(response.url).origin===origin),'REDIRECT');
          need(response.ok && response.status>=200 && response.status<300,'HTTP_ERROR');
          if(!json){discard(response);return null;}
          var length=response.headers && response.headers.get('Content-Length');
          need(length===null || length===undefined || /^\d+$/.test(length) && Number(length)<=65536,'RESPONSE_LIMIT');
          need(response.body && typeof response.body.getReader==='function','INVALID_RESPONSE');reader=response.body.getReader();
          var chunks=[],size=0;
          for(;;){var part=await reader.read();need(!stopped(),'TIMEOUT');if(part.done)break;need(part.value instanceof Uint8Array,'INVALID_RESPONSE');size+=part.value.byteLength;need(size<=65536,'RESPONSE_LIMIT');chunks.push(part.value);}
          var bytes=new Uint8Array(size),offset=0;chunks.forEach(function (c) {bytes.set(c,offset);offset+=c.byteLength;});
          var value;try {value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));} catch (_) {fail('INVALID_RESPONSE');}
          need(object(value),'INVALID_RESPONSE');return value;
        } finally {if(!reader)discard(response);}
      },ms,signal);} finally {cancel(reader);}
    }
    async function execute(signal) {
      var report={version:1,status:'refused',failureCode:null,native:{createAttempted:false,createHttpStatus:null,authenticatedFlag:null,freshBindingProven:false,endAttempted:false,endHttpStatus:null,endAcknowledged:false,topicFinished:false,syncPolls:0},
        metadata:{beforeComplete:false,afterComplete:false,terminalComplete:false,principalMatches:false,unexpectedInitialization:null,terminalConversation:null,activeConversations:null,unknownStates:null,ownedDeviceConversations:null,ownedDeviceSessions:null,unownedDeviceRows:null,messages:null,plans:null,genai:null,tools:null},
        durations:{beforeMs:null,createMs:null,verifyMs:null,endMs:null,syncMs:null,terminalMs:null,totalMs:null},limitations:{ambMappingIndependent:false,serverInitializationGuaranteedFalse:false,sessionRetirementProven:false}};
      var residue={attemptId:null,deviceId:null,conversationIds:[],sessionIds:[]};
      var before,after,binding=null,dto=null,cursor,proof=false,terminalOK=false,cleanupAmbiguous=false,identityMismatch=false,firstTick,firstWall=Date.now(),deadlineTick,deadlineWall,priorSnapshot,priorAt;
      var m=report.metadata,n=report.native,d=report.durations;
      function record(code) {if(report.failureCode===null)report.failureCode=code;}
      function elapsed(start) {return Math.max(0,Math.round(ticks()-start));}
      async function phase(name,work) {var start=ticks();try{return await work();}finally{d[name]=(d[name]||0)+elapsed(start);}}
      function remaining(reserve) {return Math.max(0,Math.min(deadlineTick-ticks(),deadlineWall-Date.now())-(reserve||0));}
      function observe(s) {
        m.activeConversations=s.counts.activeConversations;m.unknownStates=s.counts.unknownStates;
        m.ownedDeviceConversations=s.deviceConversations.length;m.ownedDeviceSessions=s.deviceSessions.length;m.unownedDeviceRows=s.unownedDeviceRows;
        ['messages','plans','genai','tools'].forEach(function (key) {m[key]=s.activity[key];});
        if(s.activity.available){var unexpected=s.activity.plans>0 || s.activity.genai>0 || s.activity.tools>0;m.unexpectedInitialization=m.unexpectedInitialization===true || unexpected;
          if(unexpected)record('UNEXPECTED_INITIALIZATION');}
        else {if(m.unexpectedInitialization!==true)m.unexpectedInitialization=null;record('ACTIVITY_UNAVAILABLE');}
        s.deviceConversations.forEach(function (r) {if(residue.conversationIds.indexOf(r.id)<0)residue.conversationIds.push(r.id);});
        s.deviceSessions.forEach(function (r) {if(residue.sessionIds.indexOf(r.id)<0)residue.sessionIds.push(r.id);});
      }
      async function metadata(phaseName,ms,userSignal) {
        var req=freeze({version:1,phase:phaseName,attemptId:residue.attemptId,deviceId:residue.deviceId}),start=ticks();
        var s=await bounded(async function (abort,stopped) {var value=await inspect(req,{signal:abort});need(!stopped(),'TIMEOUT');return snapshot(value,req);},ms,userSignal);
        var end=ticks();need(end-start<=ms+1 && s.server.finishedMs-s.server.startedMs<=end-start+3000,'PRECHECK_REFUSED');
        if(s.principalHash!==callerHash){identityMismatch=true;m.principalMatches=false;fail('IDENTITY_MISMATCH');}
        if(priorSnapshot)need(s.server.startedMs>=priorSnapshot.server.finishedMs && Math.abs((s.server.finishedMs-priorSnapshot.server.finishedMs)-(end-priorAt))<=3000,'BINDING_UNPROVEN');
        priorSnapshot=s;priorAt=end;m.principalMatches=!identityMismatch;return s;
      }
      function unchanged(oldRows,newRows) {return oldRows.every(function (old) {return newRows.some(function (r) {return same(old,r);});});}
      function prove(s) {
        need(dto && binding && before,'BINDING_UNPROVEN');
        need(s.unownedDeviceRows===0 && s.counts.unknownStates===0 && unchanged(before.conversations,s.conversations) && unchanged(before.sessions,s.sessions),'BINDING_UNPROVEN');
        need(s.conversations.length===before.conversations.length+1 && s.sessions.length===before.sessions.length+1 && s.deviceConversations.length===1 && s.deviceSessions.length===1,'BINDING_UNPROVEN');
        var c=s.deviceConversations[0],r=s.deviceSessions[0];
        need(!before.conversations.some(function (old) {return old.id===c.id;}) && !before.sessions.some(function (old) {return old.id===r.id;}),'BINDING_UNPROVEN');
        need(c.id===binding.conversationId && r.id===binding.sessionId && c.consumerId===binding.consumerId && r.consumerId===binding.consumerId && c.accountId===binding.accountId && r.accountId===binding.accountId && c.vendorId===VENDOR && r.vendorId===VENDOR && c.profileId===PROFILE && c.deviceId===residue.deviceId && r.deviceId===residue.deviceId && r.deviceType==='mweb','BINDING_UNPROVEN');
        [c,r].forEach(function (row) {need(row.createdMs>=before.server.finishedMs-999 && row.createdMs<=s.server.finishedMs,'BINDING_UNPROVEN');});
        need(ACTIVE.indexOf(c.state)>=0 && s.counts.activeConversations===1 && s.messageSessionLinks.every(function (link) {return link.conversationId===c.id && (link.sessionId===null || link.sessionId===r.id);}),'BINDING_UNPROVEN');
      }
      try {
        need(origin===ORIGIN && typeof fetchNative==='function' && typeof inspect==='function' && typeof callerHash==='string' && /^[0-9a-f]{64}$/.test(callerHash) && [uuid,now,monotonic,sleep].every(function (f) {return typeof f==='function';}),'INVALID_CONFIG');
        firstTick=ticks();need(!signal || !signal.aborted,'CANCELLED');residue.attemptId=newId();residue.deviceId=newId();
        before=await phase('beforeMs',function () {return metadata('before',15000,signal);});m.beforeComplete=true;observe(before);
        need(before.counts.activeConversations===0 && before.counts.unknownStates===0 && before.deviceConversations.length===0 && before.deviceSessions.length===0 && before.unownedDeviceRows===0,'PRECHECK_REFUSED');
        need(!signal || !signal.aborted,'CANCELLED');
        var createBody={requestTime:stamp(),deviceId:residue.deviceId,direction:'inbound',vendorId:VENDOR,consumerId:'',consumerAccountId:'',deviceType:'mweb',contextData:{global_context_profile:PROFILE,nowassist:'true'}};
        n.createAttempted=true;
        try {dto=await phase('createMs',function () {return request('/api/now/v2/cs/session','POST',createBody,{},15000,signal,true,function (s) {n.createHttpStatus=s;});});}
        finally {deadlineTick=ticks()+45000;deadlineWall=Date.now()+45000;}
        need(!has(dto,'result'),'INVALID_RESPONSE');
        n.authenticatedFlag=has(dto,'guestSessionIdentifier') ? dto.guestSessionIdentifier===null : null;
        need(dto.guestSessionIdentifier===null,'UNAUTHENTICATED');
        ['lastMessage','messages','history','resume','resumeMessage'].forEach(function (key) {need(!has(dto,key) || dto[key]===null && (key==='lastMessage' || key==='messages'),'EXISTING_CONVERSATION');});
        need(!has(dto,'conversationState') || dto.conversationState==='CONVERSATION_STARTED','EXISTING_CONVERSATION');
        var account=has(dto,'consumerAccountId')?dto.consumerAccountId:dto.consumerAcctId;
        need(!has(dto,'consumerAccountId') || !has(dto,'consumerAcctId') || dto.consumerAccountId===dto.consumerAcctId,'INVALID_BINDING');
        need([dto.sessionId,dto.conversationId,dto.consumerId,account].every(function (value) {return typeof value==='string' && value.length>0 && value.length<=8192;}) && channel(dto.channelId),'INVALID_BINDING');
        need(!before.conversations.some(function (r) {return r.id===dto.conversationId;}) && !before.sessions.some(function (r) {return r.id===dto.sessionId;}),'EXISTING_CONVERSATION');
        need(Number.isSafeInteger(dto.serialNumber) && dto.serialNumber>=-1,'INVALID_SEQUENCE');cursor=dto.serialNumber===-1?0:dto.serialNumber;
        binding={sessionId:dto.sessionId,conversationId:dto.conversationId,consumerId:dto.consumerId,accountId:account,channel:channel(dto.channelId)};
      } catch(e) {record(failure(e));}
      if(n.createAttempted) {
        try {
          after=await phase('verifyMs',function () {return metadata('after',Math.min(15000,remaining(15000)),null);});m.afterComplete=true;observe(after);
          prove(after);proof=true;n.freshBindingProven=true;
        } catch(e) {cleanupAmbiguous=true;record(failure(e));}
        // A cancelled operation with a fully observed DTO can still be cleaned
        // only if all binding checks above succeeded; cancellation never weakens proof.
        if(signal && signal.aborted)record('CANCELLED');
        if(proof) {
          try {
            var body={type:'actionMessage',source:'client',data:{actionMessage:{topicId:binding.conversationId,systemActionName:'endChat',type:'EndChat'},conversationId:binding.conversationId,deviceType:'mweb',sessionId:binding.sessionId,messageId:newId(),direction:'inbound',sendTime:stamp()}};
            need(remaining(15000)>0,'TIMEOUT');n.endAttempted=true;
            try {await phase('endMs',function () {return request('/api/now/cs_message','POST',body,{'amb-channel':'/cs/messages/'+binding.channel,'X-User-Activity':'true'},Math.min(10000,remaining(15000)),null,false,function (s) {n.endHttpStatus=s;});});n.endAcknowledged=true;}
            catch(e) {cleanupAmbiguous=true;record(failure(e));}
            var seen=new Set();
            for(var poll=0;poll<6 && !n.topicFinished && remaining(15000)>0;poll++) {
              var query=new URLSearchParams({serialNumber:String(cursor),iefix:newId(),shouldInitializeConversation:'false',conversationId:binding.conversationId});
              n.syncPolls++;
              var synced=await phase('syncMs',function () {return request('/api/now/v1/cs/consumerAccount/'+binding.accountId+'/sync?'+query,'GET',undefined,{'Session-Id':binding.sessionId,'Guest-Session-Identifier':'null'},Math.min(3000,remaining(15000)),null,true,function () {});});
              need(!has(synced,'result') && Array.isArray(synced.messages),'INVALID_RESPONSE');need(synced.messages.length<=128,'RESPONSE_LIMIT');
              for(var i=0;i<synced.messages.length;i++) {
                var msg=synced.messages[i];
                need(object(msg) && Number.isSafeInteger(msg.serialNumber) && msg.serialNumber===cursor+1 && typeof msg.messageId==='string' && /^[A-Za-z0-9_-]{1,128}$/.test(msg.messageId) && !seen.has(msg.messageId) && msg.conversationId===binding.conversationId && (!has(msg,'sessionId') || msg.sessionId===binding.sessionId) && (!has(msg,'channelId') || channel(msg.channelId)===binding.channel),'INVALID_SEQUENCE');
                if(msg.queueMsgDataType==='actionMessage' && object(msg.actionMessage) && msg.actionMessage.type==='TopicFinished') {
                  need(!has(msg.actionMessage,'topicId') || msg.actionMessage.topicId===binding.conversationId,'INVALID_SEQUENCE');n.topicFinished=true;
                }
                seen.add(msg.messageId);cursor=msg.serialNumber;
              }
              if(!n.topicFinished && poll<5 && remaining(15000)>0)await phase('syncMs',function () {return bounded(function () {return sleep(200);},Math.min(1000,remaining(15000)),null);});
            }
          } catch(e) {cleanupAmbiguous=true;record(failure(e));}
        }
        if(!n.endAcknowledged || !n.topicFinished){cleanupAmbiguous=true;record('CLEANUP_UNCONFIRMED');}
        // Always perform the independent terminal read, even after refused proof.
        // It can report residue and terminal state, but never authorize a late End.
        try {
          var terminal=await phase('terminalMs',function () {return metadata('terminal',Math.min(15000,remaining()),null);});m.terminalComplete=true;observe(terminal);
          var candidate=binding && terminal.deviceConversations.find(function (r) {return r.id===binding.conversationId;});
          m.terminalConversation=!!(proof && candidate && candidate.consumerId===binding.consumerId && candidate.accountId===binding.accountId && candidate.vendorId===VENDOR && candidate.profileId===PROFILE && TERMINAL.indexOf(candidate.state)>=0);
          terminalOK=m.terminalConversation && terminal.counts.activeConversations===0 && terminal.counts.unknownStates===0 && terminal.unownedDeviceRows===0;
          if(proof) {
            var initialCandidate=after.deviceConversations[0];
            terminalOK=terminalOK && terminal.conversations.length===after.conversations.length && terminal.sessions.length===after.sessions.length && terminal.deviceConversations.length===1 && terminal.deviceSessions.length===1 && unchanged(before.conversations,terminal.conversations) && unchanged(after.sessions,terminal.sessions)
              && candidate.createdMs===initialCandidate.createdMs && candidate.updatedMs>=initialCandidate.updatedMs && candidate.modCount>=initialCandidate.modCount
              && terminal.messageSessionLinks.every(function (link) {return link.conversationId===binding.conversationId && (link.sessionId===null || link.sessionId===binding.sessionId);});
          }
          need(terminalOK,'TERMINAL_UNCONFIRMED');
        } catch(e) {cleanupAmbiguous=true;record(failure(e)==='TIMEOUT'?'TIMEOUT':'TERMINAL_UNCONFIRMED');}
        if(signal && signal.aborted)record('CANCELLED');
        report.status=cleanupAmbiguous || !terminalOK ? 'uncertain' : report.failureCode===null ? 'passed' : 'failed';
      }
      try {d.totalMs=firstTick===undefined?Math.max(0,Date.now()-firstWall):elapsed(firstTick);} catch (_) {d.totalMs=Math.max(0,Date.now()-firstWall);record('INVALID_CONFIG');if(n.createAttempted)report.status='uncertain';}
      dto=null;binding=null;before=null;after=null;priorSnapshot=null;callerHash=null;
      return freeze({report:report,residue:residue});
    }
    return Object.freeze({run:function (config) {if(!once)once=execute(config && config.signal);return once;}});
  }
  return Object.freeze({createNativeOAuthSessionProbe:createNativeOAuthSessionProbe});
}));
