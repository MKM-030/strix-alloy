/* Isolated native-session diagnostic. Loading this file performs no IO.
 * Native wire sources: authenticated-chat-contract extracts 01-16,21-23,26,
 * ui-mega vv/Fm and sn-http-request Ft/Pe: HTTP JSON is the DTO, not .result.
 */
(function (root, factory) {
  'use strict';
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SccNativeSessionProbe = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  var ORIGIN = 'https://soprasteriaassvsdemo14.service-now.com';
  var TRANSACTION = 'Interface=Chat,Interface-Type=Unknown,Interface-Name=Unknown,Interface-SysID=0d5bb8b9730303004ab2369f2ef6a737';
  // Local diagnostic policy, not native wire constants.
  var CREATE_MS = 15000, CLEANUP_MS = 15000, REQUEST_MS = 4000, PRECHECK_MS = 10000, VERIFY_MS = 6000;
  var MAX_BYTES = 65536, MAX_MESSAGES = 128, MAX_POLLS = 6;
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  function Failure(code) { this.code = code; }
  function fail(code) { throw new Failure(code); }
  function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function serial(value) { return Number.isSafeInteger(value) && value >= -1; }
  function createNativeSessionProbe(options) {
    options = options || {};
    var origin = options.origin, token = options.csrfToken;
    var fetchImpl = options.fetchImpl || function (url, config) { return root.fetch(url, config); };
    var uuid = options.uuid || function () { return root.crypto.randomUUID(); };
    var now = options.now || function () { return Date.now(); };
    var monotonic = options.monotonic || function () { return root.performance.now(); };
    var sleep = options.sleep || function (ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); };
    var prepareAttempt = options.prepareAttempt, verifyCreatedBinding = options.verifyCreatedBinding;
    var once, usedIds = new Set();
    function safeId(value) {
      return typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value)
        && (!token || value.indexOf(token) === -1) ? value : null;
    }
    function newId() {
      var value = uuid();
      if (typeof value !== 'string' || !UUID.test(value) || usedIds.has(value)
          || (token && value.indexOf(token) !== -1)) fail('INVALID_CONFIG');
      usedIds.add(value); return value;
    }
    function stamp() {
      var value = now();
      if (!Number.isSafeInteger(value) || value < 0) fail('INVALID_CONFIG');
      return value;
    }
    function ticks() {
      var value = monotonic();
      if (!Number.isFinite(value)) fail('INVALID_CONFIG');
      return value;
    }
    function code(error, fallback) { return error instanceof Failure ? error.code : fallback; }
    function exact(value, keys) {
      return object(value) && Object.keys(value).length === keys.length
        && keys.every(function (key) { return Object.prototype.hasOwnProperty.call(value, key); });
    }
    function snapshot(value) {
      if (!Array.isArray(value) || value.length > 512) fail('PRECHECK_REFUSED');
      var ids = new Set();
      for (var i = 0; i < value.length; i++) {
        var id = value[i];
        if (!safeId(id) || ids.has(id)) fail('PRECHECK_REFUSED');
        ids.add(id);
      }
      return ids;
    }
    function channelSuffix(value) {
      // Source03 extracts the last segment, not a particular raw prefix. Local
      // policy excludes URLs, query/fragment syntax, empty/dot segments and controls.
      if (typeof value !== 'string' || value.length > 512 || !/^\/?[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*$/.test(value)) return null;
      var parts = value.split('/');
      if (parts.some(function (part) { return part.length > 128; })) return null;
      return safeId(parts[parts.length - 1]);
    }
    async function proofCallback(callback, args, budget, signal) {
      if (!(budget > 0)) fail('TIMEOUT');
      var controller = new AbortController(), timer, abort;
      var stopped = new Promise(function (_, reject) {
        timer = setTimeout(function () { controller.abort(); reject(new Failure('TIMEOUT')); }, budget);
        if (signal) {
          abort = function () { controller.abort(); reject(new Failure('CANCELLED')); };
          signal.addEventListener('abort', abort, {once: true});
          if (signal.aborted) abort();
        }
      });
      try {
        return await Promise.race([stopped, Promise.resolve().then(function () {
          if (controller.signal.aborted) fail('CANCELLED');
          return callback(Object.freeze(args), {signal: controller.signal});
        })]);
      } finally {
        clearTimeout(timer);
        if (signal && abort) signal.removeEventListener('abort', abort);
        controller.abort();
      }
    }
    async function request(path, method, body, headers, budget, signal, json) {
      if (!(budget > 0)) fail('TIMEOUT');
      var controller = new AbortController(), reader, timer, abort, expired = false;
      var timeout = new Promise(function (_, reject) {
        timer = setTimeout(function () { expired = true; controller.abort(); reject(new Failure('TIMEOUT')); }, budget);
      });
      if (signal) {
        abort = function () { controller.abort(); };
        signal.addEventListener('abort', abort, {once: true});
        if (signal.aborted) abort();
      }
      var work = async function () {
        var response = await fetchImpl(origin + path, {
          method: method, credentials: 'same-origin', redirect: 'error', mode: 'same-origin',
          headers: Object.assign({'Accept': 'application/json', 'Content-Type': 'application/json',
            'X-UserToken': token, 'X-Transaction-Source': TRANSACTION}, headers),
          body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal
        });
        if (expired) {
          if (response && response.body) response.body.cancel().catch(function () {});
          fail('TIMEOUT');
        }
        if (!response || response.redirected || (response.url && new URL(response.url).origin !== origin)) fail('REDIRECT');
        if (!response.ok || response.status < 200 || response.status >= 300) fail('HTTP_ERROR');
        if (!json) {
          if (response.body) response.body.cancel().catch(function () {});
          return null;
        }
        var length = response.headers && response.headers.get('Content-Length');
        if (length !== null && length !== undefined && (!/^\d+$/.test(length) || Number(length) > MAX_BYTES)) fail('RESPONSE_LIMIT');
        if (!response.body || typeof response.body.getReader !== 'function') fail('INVALID_RESPONSE');
        reader = response.body.getReader();
        var chunks = [], size = 0;
        for (;;) {
          var chunk = await reader.read();
          if (expired) fail('TIMEOUT');
          if (chunk.done) break;
          size += chunk.value.byteLength;
          if (size > MAX_BYTES) fail('RESPONSE_LIMIT');
          chunks.push(chunk.value);
        }
        var bytes = new Uint8Array(size), offset = 0;
        chunks.forEach(function (chunk) { bytes.set(chunk, offset); offset += chunk.byteLength; });
        var value;
        try { value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)); }
        catch (_) { fail('INVALID_RESPONSE'); }
        if (!object(value)) fail('INVALID_RESPONSE');
        return value;
      };
      try { return await Promise.race([work(), timeout]); }
      finally {
        clearTimeout(timer);
        if (signal && abort) signal.removeEventListener('abort', abort);
        // Do not wait for a remote stream's cancellation acknowledgement.
        if (reader) reader.cancel().catch(function () {});
        controller.abort();
      }
    }
    async function execute(signal) {
      var result = {version: 1, passed: false, authenticated: false,
        binding: {sessionId: null, consumerAccountId: null, conversationId: null, channelSuffix: null},
        cleanup: {attempted: false, acknowledged: false, completed: false, uncertain: false},
        phases: [], failureCode: null};
      var binding = result.binding, cleanup = result.cleanup, created, cursor, needsVerification = false;
      var requestId, deviceId, oldSessions, oldConversations;
      function recordFailure(value) { if (result.failureCode === null) result.failureCode = value; }
      async function phase(name, task) {
        var start = ticks();
        try { return await task(); }
        finally { result.phases.push({phase: name, elapsed_ms: Math.min(60000, Math.max(0, Math.round(ticks() - start)))}); }
      }
      try {
        if (origin !== ORIGIN || typeof token !== 'string' || !token.length || token.length > 8192
            || /[^\x21-\x7e]/.test(token) || typeof fetchImpl !== 'function'
            || typeof uuid !== 'function' || typeof now !== 'function' || typeof monotonic !== 'function'
            || typeof sleep !== 'function' || typeof prepareAttempt !== 'function'
            || typeof verifyCreatedBinding !== 'function') fail('INVALID_CONFIG');
        if (signal && signal.aborted) fail('CANCELLED');
        deviceId = newId(); requestId = newId();
        var prepared = await phase('precheck', function () {
          return proofCallback(prepareAttempt, {requestId: requestId, deviceId: deviceId}, PRECHECK_MS, signal);
        });
        if (!exact(prepared, ['version', 'requestId', 'deviceId', 'allowed', 'existingSessionIds', 'existingConversationIds'])
            || prepared.version !== 1 || prepared.requestId !== requestId || prepared.deviceId !== deviceId
            || prepared.allowed !== true) fail('PRECHECK_REFUSED');
        oldSessions = snapshot(prepared.existingSessionIds);
        oldConversations = snapshot(prepared.existingConversationIds);
        if (signal && signal.aborted) fail('CANCELLED');
        var createBody = {requestTime: stamp(), deviceId: deviceId, direction: 'inbound',
          vendorId: 'c2f0b8f187033200246ddd4c97cb0bb9', consumerId: '', consumerAccountId: '',
          deviceType: 'mweb', contextData: {global_context_profile: 'c623e20f93374354e7f2b9fa6aba1081', nowassist: 'true'}};
        cleanup.uncertain = true;
        created = await phase('create', function () {
          return request('/api/now/v2/cs/session', 'POST', createBody, {}, CREATE_MS, signal, true);
        });
        if (Object.prototype.hasOwnProperty.call(created, 'result')) fail('INVALID_RESPONSE');
        binding.sessionId = safeId(created.sessionId);
        binding.conversationId = safeId(created.conversationId);
        var account = created.consumerAccountId || created.consumerAcctId;
        if (created.consumerAccountId && created.consumerAcctId && created.consumerAccountId !== created.consumerAcctId) account = null;
        binding.consumerAccountId = safeId(account);
        binding.channelSuffix = channelSuffix(created.channelId);
        var complete = Object.keys(binding).every(function (key) { return binding[key] !== null; });
        result.authenticated = complete && created.guestSessionIdentifier === null;
        if (!complete) fail('INVALID_BINDING');
        if (created.guestSessionIdentifier !== null) fail('UNAUTHENTICATED');
        // Native source03/07 consumes lastMessage as a resume and messages as history.
        // State other than the native started state is conservatively refused.
        if ((created.lastMessage !== undefined && created.lastMessage !== null)
            || (created.messages !== undefined && created.messages !== null)
            || (created.conversationState && created.conversationState !== 'CONVERSATION_STARTED')
            || oldSessions.has(binding.sessionId) || oldConversations.has(binding.conversationId)) fail('EXISTING_CONVERSATION');
        needsVerification = true;
        if (!serial(created.serialNumber)) fail('INVALID_SEQUENCE');
        cursor = created.serialNumber === -1 ? 0 : created.serialNumber;
        if (signal && signal.aborted) fail('CANCELLED');
      } catch (error) {
        recordFailure(signal && signal.aborted ? 'CANCELLED' : code(error, 'REQUEST_FAILED'));
      }
      if (needsVerification) {
        // This reserve starts after creation and never inherits user cancellation.
        var deadline;
        try {
          deadline = ticks() + CLEANUP_MS;
          var verified = await phase('verify_binding', function () {
            return proofCallback(verifyCreatedBinding, {requestId: requestId, deviceId: deviceId,
              sessionId: binding.sessionId, consumerAccountId: binding.consumerAccountId,
              conversationId: binding.conversationId}, Math.min(VERIFY_MS, deadline - ticks()), null);
          });
          if (!exact(verified, ['version', 'requestId', 'deviceId', 'sessionId', 'consumerAccountId',
            'conversationId', 'callerOwns', 'profileMatches', 'deviceMatches', 'fresh'])
              || verified.version !== 1 || verified.requestId !== requestId || verified.deviceId !== deviceId
              || verified.sessionId !== binding.sessionId || verified.consumerAccountId !== binding.consumerAccountId
              || verified.conversationId !== binding.conversationId || verified.callerOwns !== true
              || verified.profileMatches !== true || verified.deviceMatches !== true || verified.fresh !== true) fail('BINDING_UNPROVEN');
          if (!(deadline - ticks() > 0)) fail('TIMEOUT');
          var endBody = {type: 'actionMessage', source: 'client', data: {
            actionMessage: {topicId: binding.conversationId, systemActionName: 'endChat', type: 'EndChat'},
            conversationId: binding.conversationId, deviceType: 'mweb', sessionId: binding.sessionId,
            messageId: newId(), direction: 'inbound', sendTime: stamp()}};
          cleanup.attempted = true;
          try {
            await phase('end_chat', function () {
              return request('/api/now/cs_message', 'POST', endBody,
                {'amb-channel': '/cs/messages/' + binding.channelSuffix, 'X-User-Activity': 'true'},
                Math.min(REQUEST_MS, deadline - ticks()), null, false);
            });
            cleanup.acknowledged = true;
          } catch (error) { recordFailure(code(error, 'REQUEST_FAILED')); }
          if (cursor !== undefined) {
            var seen = new Set();
            for (var poll = 0; poll < MAX_POLLS && !cleanup.completed; poll++) {
              var query = new URLSearchParams({serialNumber: String(cursor), iefix: newId(),
                shouldInitializeConversation: 'false', conversationId: binding.conversationId});
              var synced = await phase('sync', function () {
                return request('/api/now/v1/cs/consumerAccount/' + binding.consumerAccountId + '/sync?' + query,
                  'GET', undefined, {'Session-Id': binding.sessionId, 'Guest-Session-Identifier': 'null'},
                  Math.min(REQUEST_MS, deadline - ticks()), null, true);
              });
              if (!Array.isArray(synced.messages)) fail('INVALID_RESPONSE');
              if (synced.messages.length > MAX_MESSAGES) fail('RESPONSE_LIMIT');
              for (var i = 0; i < synced.messages.length; i++) {
                var message = synced.messages[i];
                if (!object(message) || !Number.isSafeInteger(message.serialNumber) || message.serialNumber !== cursor + 1
                    || !safeId(message.messageId) || seen.has(message.messageId)
                    || message.conversationId !== binding.conversationId
                    || (message.sessionId !== undefined && message.sessionId !== binding.sessionId)
                    || (message.channelId !== undefined && channelSuffix(message.channelId) !== binding.channelSuffix)) continue;
                seen.add(message.messageId); cursor = message.serialNumber;
                if (message.queueMsgDataType === 'actionMessage' && object(message.actionMessage)
                    && message.actionMessage.type === 'TopicFinished'
                    && (message.actionMessage.topicId === undefined
                      || message.actionMessage.topicId === binding.conversationId)) cleanup.completed = true;
              }
              if (!cleanup.completed && poll + 1 < MAX_POLLS) {
                // Sleep is also bounded by the cleanup reserve, including injected sleepers.
                var remaining = deadline - ticks();
                if (!(remaining > 0)) fail('TIMEOUT');
                var sleepTimer;
                try {
                  await Promise.race([sleep(Math.min(200, remaining)), new Promise(function (_, reject) {
                    sleepTimer = setTimeout(function () { reject(new Failure('TIMEOUT')); }, remaining);
                  })]);
                } finally { clearTimeout(sleepTimer); }
              }
            }
          }
        } catch (error) { recordFailure(code(error, 'REQUEST_FAILED')); }
        cleanup.uncertain = !cleanup.completed;
        if (!cleanup.completed) recordFailure('CLEANUP_UNCONFIRMED');
      }
      if (signal && signal.aborted) recordFailure('CANCELLED');
      result.passed = result.authenticated && cleanup.acknowledged && cleanup.completed && result.failureCode === null;
      Object.freeze(binding); Object.freeze(cleanup);
      result.phases.forEach(Object.freeze); Object.freeze(result.phases);
      return Object.freeze(result);
    }
    return Object.freeze({run: function (config) {
      if (!once) once = execute(config && config.signal);
      return once;
    }});
  }
  return Object.freeze({createNativeSessionProbe: createNativeSessionProbe});
}));
