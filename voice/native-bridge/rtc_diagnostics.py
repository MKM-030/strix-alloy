"""Optional, bounded RTC metadata. No addresses, SDP, credentials or identifiers are logged."""
import asyncio
from collections import Counter
import ipaddress
import json
import logging
import os

_LOG = logging.getLogger('rtc_media_diagnostics')
_STATES = {'new','connecting','connected','disconnected','failed','closed','checking','completed','gathering','complete'}
_TYPES = {'host','srflx','prflx','relay'}


def _state(value):
    return value if value in _STATES else 'unknown'


def _family(value):
    try:
        return 'IPv' + str(ipaddress.ip_address(value).version)
    except (ValueError,TypeError):
        return 'mDNS' if isinstance(value,str) and value.endswith('.local') else 'unknown'


def _key(kind,protocol,address):
    return '|'.join((kind if kind in _TYPES else 'other',
        protocol.lower() if isinstance(protocol,str) and protocol.lower() in {'udp','tcp'} else 'other',
        _family(address)))


def _sdp(value):
    sections,counts,bundle = [],Counter(),[]
    session_fragment = None
    if not isinstance(value,str):
        return {'bytes':0,'candidates':{},'sections':[],'bundle':[]}
    for line in value.splitlines():
        if line.startswith('m='):
            kind=line[2:].split(' ',1)[0]
            sections.append({'kind':kind if kind in {'audio','video','application'} else 'other',
                'mid':None,'ufrag':session_fragment})
        elif line.startswith('a=group:BUNDLE '):
            bundle=line[15:].split()[:16]
        elif line.startswith('a=mid:') and sections:
            token=line[6:]
            sections[-1]['mid']=token if 0<len(token)<=64 else None
        elif line.startswith('a=ice-ufrag:'):
            token=line[12:]
            token=token if 0<len(token)<=256 else None
            if sections:
                sections[-1]['ufrag']=token
            else:
                session_fragment=token
        elif line.startswith('a=candidate:'):
            fields=line[12:].split()
            if len(fields)>=8:
                counts[_key(fields[7],fields[2],fields[4])]+=1
            else:
                counts['other|other|unknown']+=1
    return {'bytes':len(value.encode('utf-8',errors='replace')),
        'candidates':dict(sorted(counts.items())),'sections':sections,'bundle':bundle}


def _equal(left,right):
    return left==right if left is not None and right is not None else 'unknown'


def _consistency(values):
    if any(value is False for value in values):
        return False
    return True if values and all(value is True for value in values) else 'unknown'


def _ice_transports(peer):
    found=[]
    for transceiver in peer.getTransceivers():
        for endpoint in (transceiver.sender,transceiver.receiver):
            dtls=getattr(endpoint,'transport',None)
            ice=getattr(dtls,'transport',None)
            if ice is not None and all(ice is not existing for existing in found):
                found.append(ice)
    dtls=getattr(getattr(peer,'sctp',None),'transport',None)
    ice=getattr(dtls,'transport',None)
    if ice is not None and all(ice is not existing for existing in found):
        found.append(ice)
    return found


def _candidate_counts(candidates):
    return dict(sorted(Counter(_key(getattr(c,'type',None),getattr(c,'protocol',None),
        getattr(c,'ip',None)) for c in candidates).items()))


class MediaDiagnosticBudget:
    def __init__(self,raw='0'):
        self.enabled=raw=='1'
        self.used=False

    def reserve(self,peer):
        return self.reserve_factory(lambda:peer)

    def reserve_factory(self,peer_factory):
        if not self.enabled or self.used:
            return None
        self.used=True
        try:
            return _MediaDiagnostics(peer_factory())
        except Exception:
            return None


class _StunActivity:
    """One-call, post-gather counters. Never parses or retains packet contents.

    Response counters cover aioice's matched transactions only, including
    duplicates; they do not assert authentication or successful nomination.
    """
    _KEYS = ('tx_request','tx_response','tx_error','tx_indication',
        'rx_datagram','rx_request','rx_response_matched','rx_error_matched',
        'rx_error_400_matched','rx_error_487_matched','rx_error_other_matched',
        'binding_bad_request','binding_bad_request_username_mismatch',
        'binding_bad_request_auth_other','nonbinding_bad_request','role_conflict')
    _CLASS_KEYS = {0x0000:'request',0x0100:'response',0x0110:'error',0x0010:'indication'}

    def __init__(self, peer):
        self.peer = peer
        self.closed = False
        self.limited = False
        self.counts = dict.fromkeys(self._KEYS, 0)
        self._connections = set()
        self._gatherers = set()
        self._protocols = set()
        self._transactions = set()
        self._restores = []
        self._listeners = []
        self._listen(peer, 'signalingstatechange', self.refresh)
        self.refresh()

    def _bump(self, key):
        if not self.closed and key in self.counts:
            self.counts[key] = min(2147483647, self.counts[key] + 1)

    def _listen(self, emitter, event, callback):
        try:
            emitter.on(event, callback)
            self._listeners.append((emitter, event, callback))
        except Exception:
            self.limited = True

    def _wrap(self, obj, name, observe):
        original = getattr(obj, name)
        had_own = name in vars(obj)
        own = vars(obj).get(name)
        def wrapper(*args, **kwargs):
            if not self.closed:
                try:
                    observe(*args, **kwargs)
                except Exception:
                    self.limited = True
            # Observer failure never changes the original call or exception.
            return original(*args, **kwargs)
        setattr(obj, name, wrapper)
        self._restores.append((obj, name, had_own, own, wrapper))

    def refresh(self):
        """Synchronous: completed fires before aiortc schedules ICE checks."""
        if self.closed:
            return
        try:
            for transport in _ice_transports(self.peer):
                gatherer = transport.iceGatherer
                if gatherer not in self._gatherers:
                    if len(self._gatherers) >= 16:
                        self.limited = True
                        continue
                    self._gatherers.add(gatherer)
                    self._listen(gatherer, 'statechange', self.refresh)
                connection = getattr(gatherer, '_connection', None)
                if connection is None or getattr(gatherer, 'state', None) != 'completed':
                    continue
                if connection not in self._connections:
                    self._wrap(connection, 'request_received', self._received_request)
                    self._wrap(connection, 'respond_error',
                        lambda request, addr, protocol, error_code, connection=connection:
                            self._rejected_request(connection, request, error_code))
                    self._connections.add(connection)
                for protocol in getattr(connection, '_protocols', ()):
                    if protocol in self._protocols:
                        continue
                    if len(self._protocols) >= 16:
                        self.limited = True
                        continue
                    self._wrap(protocol, 'send_stun',
                        lambda message, addr, protocol=protocol: self._sent(protocol, message))
                    self._wrap(protocol, 'datagram_received',
                        lambda data, addr: self._bump('rx_datagram'))
                    self._protocols.add(protocol)
        except Exception:
            self.limited = True

    def _sent(self, protocol, message):
        category = self._CLASS_KEYS.get(getattr(message, 'message_class', None))
        if category is not None:
            self._bump('tx_' + category)
        transaction = getattr(protocol, 'transactions', {}).get(message.transaction_id)
        if transaction is None or transaction in self._transactions:
            return
        # Bound memory even if a long call creates ongoing consent transactions.
        if len(self._transactions) >= 128:
            self.limited = True
            return
        self._wrap(transaction, 'response_received', self._received_response)
        self._transactions.add(transaction)

    def _received_request(self, message, addr, protocol, raw_data):
        self._bump('rx_request')

    def _received_response(self, message, addr):
        category = self._CLASS_KEYS.get(getattr(message, 'message_class', None))
        if category == 'response':
            self._bump('rx_response_matched')
        elif category == 'error':
            self._bump('rx_error_matched')
            code = message.attributes.get('ERROR-CODE', (None,))[0]
            suffix = str(code) if code in (400, 487) else 'other'
            self._bump('rx_error_' + suffix + '_matched')

    def _rejected_request(self, connection, request, error_code):
        code = error_code[0]
        if code == 487:
            self._bump('role_conflict')
        elif code == 400:
            if getattr(request, 'message_method', None) != 1:
                self._bump('nonbinding_bad_request')
                return
            self._bump('binding_bad_request')
            remote = getattr(connection, 'remote_username', None)
            # Correlation only: aioice verifies integrity before username.
            mismatch = remote is not None and request.attributes.get('USERNAME') != (
                connection.local_username + ':' + remote)
            self._bump('binding_bad_request_username_mismatch' if mismatch else
                'binding_bad_request_auth_other')

    def snapshot(self):
        return {'available': bool(self._protocols),
            'attached_protocols': len(self._protocols),
            'observed_connections': len(self._connections),
            'coverage_limited': self.limited,
            'post_gather_only': True,
            'tx_counts_are': 'send_stun_invocations_not_wire_confirmation',
            'unmatched_stun_responses_observed': False,
            'matched_response_means': 'transaction_id_match_only',
            'auth_rejection_means': 'binding_400_with_username_correlation_only',
            'counts': dict(self.counts)}

    def close(self):
        if self.closed:
            return
        self.closed = True
        for emitter, event, callback in reversed(self._listeners):
            try:
                emitter.remove_listener(event, callback)
            except Exception:
                pass
        self._listeners.clear()
        for obj, name, had_own, own, wrapper in reversed(self._restores):
            try:
                if getattr(obj, name, None) is wrapper:
                    if had_own:
                        setattr(obj, name, own)
                    else:
                        delattr(obj, name)
            except Exception:
                pass
        self._restores.clear()
        self._transactions.clear()


class _MediaDiagnostics:
    def __init__(self,peer):
        self.peer=peer
        self.snapshots=0
        self._stages=set()
        self._outcome_seen=False
        self._lock=asyncio.Lock()
        self._remote=None
        self._offer_public=None
        self._trickle=[]
        self._checkpoint_task=None
        self._stun=_StunActivity(peer)
        try:
            peer.on('connectionstatechange',self._on_state)
        except Exception:
            pass

    async def _on_state(self):
        state=getattr(self.peer,'connectionState',None)
        try:
            if state in {'connected','failed'}:
                if not self._outcome_seen:
                    self._outcome_seen=True
                    await self._snapshot(state)
            elif state=='closed':
                await self._snapshot(state)
        finally:
            if state=='closed':
                if self._checkpoint_task is not None:
                    self._checkpoint_task.cancel()
                self._stun.close()
                self._remote=None
                self._trickle.clear()

    async def _checkpoint(self):
        try:
            await asyncio.sleep(10)
            if not self._outcome_seen and getattr(self.peer,'connectionState',None) != 'closed':
                self._outcome_seen=True
                await self._snapshot('checkpoint')
        except asyncio.CancelledError:
            pass

    def observe_trickle(self,value):
        if self.snapshots>=3 or len(self._trickle)>=128:
            return
        try:
            fragment=None
            fields=value['candidate'].split()
            for index,field in enumerate(fields[:-1]):
                if field=='ufrag' and 0<len(fields[index+1])<=256:
                    fragment=fields[index+1]
                    break
            self._trickle.append((value.get('sdpMid'),value.get('sdpMLineIndex'),fragment))
        except Exception:
            pass

    async def observe_offer(self,remote_sdp,local_sdp,response_body):
        try:
            remote,local=_sdp(remote_sdp),_sdp(local_sdp)
            self._remote=remote
            wire_sdp=None
            shape=False
            try:
                parsed=json.loads(response_body)
                shape=(type(parsed) is dict and set(parsed)=={'sdp'} and
                    type(parsed['sdp']) is dict and set(parsed['sdp'])=={'type','sdp'} and
                    parsed['sdp']['type']=='answer' and isinstance(parsed['sdp']['sdp'],str))
                if shape:
                    wire_sdp=parsed['sdp']['sdp']
            except Exception:
                pass
            wire=_sdp(wire_sdp)
            rows=[]
            for index,section in enumerate(local['sections'][:16]):
                target=wire['sections'][index] if index<len(wire['sections']) else {}
                source=remote['sections'][index] if index<len(remote['sections']) else {}
                bundle_sections=[s for s in remote['sections'] if s['mid'] in remote['bundle']]
                first=bundle_sections[0].get('ufrag') if bundle_sections else None
                rows.append({'index':index,'kind':section['kind'],
                    'wire_ufrag_matches_local':_equal(section.get('ufrag'),target.get('ufrag')),
                    'wire_mid_matches_local':_equal(section.get('mid'),target.get('mid')),
                    'local_remote_mid_matches':_equal(section.get('mid'),source.get('mid')),
                    'remote_bundle_ufrag_matches_first':_equal(source.get('ufrag'),first) if source.get('mid') in remote['bundle'] else 'unknown'})
            self._offer_public={'wire':{'nested_answer_shape':shape,
                'sdp_matches_local':wire_sdp==local_sdp if wire_sdp is not None else False,
                'response_body_bytes':len(response_body) if isinstance(response_body,(bytes,bytearray)) else 0},
                'sdp_bytes':{'remote_offer':remote['bytes'],'local_answer':local['bytes'],'wire_answer':wire['bytes']},
                'sdp_candidates':{'remote_offer':remote['candidates'],'local_answer':local['candidates'],'wire_answer':wire['candidates']},
                'm_sections':rows,'m_section_count':len(local['sections']),
                'm_sections_truncated':len(local['sections'])>16}
            await self._snapshot('offer')
            if self._checkpoint_task is None and getattr(self.peer,'connectionState',None) != 'closed':
                self._checkpoint_task=asyncio.create_task(self._checkpoint())
        except Exception:
            pass

    def _trickle_public(self):
        mids,indices,both,fragments=[],[],[],[]
        sections=self._remote['sections'] if self._remote else []
        for mid,index,fragment in self._trickle:
            by_mid=next((s for s in sections if s['mid']==mid and mid is not None),None)
            by_index=sections[index] if type(index) is int and 0<=index<len(sections) else None
            mids.append(bool(by_mid) if sections else 'unknown')
            indices.append(bool(by_index) if sections else 'unknown')
            both.append(by_mid is not None and by_index is not None and by_mid is by_index if sections else 'unknown')
            fragments.append(_equal(fragment,by_mid.get('ufrag') if by_mid else None))
        return {'count':len(self._trickle),'mid_matches_offer':_consistency(mids),
            'index_matches_offer':_consistency(indices),'mid_index_consistent':_consistency(both),
            'username_fragment_matches_offer':_consistency(fragments),
            'username_fragment_present_count':sum(fragment is not None for _,_,fragment in self._trickle)}

    async def _snapshot(self,stage):
        try:
            async with self._lock:
                if self.snapshots>=3 or stage in self._stages:
                    return
                self.snapshots+=1
                self._stages.add(stage)
                value={'stage':stage,'snapshot':self.snapshots,
                    'connection_state':_state(getattr(self.peer,'connectionState',None)),
                    'ice_state':_state(getattr(self.peer,'iceConnectionState',None)),
                    'gathering_state':_state(getattr(self.peer,'iceGatheringState',None)),
                    'trickle':self._trickle_public()}
                value.update(self._offer_public or {})
                value['stun_activity']=self._stun.snapshot()
                try:
                    transports=_ice_transports(self.peer)
                    local,remote=[],[]
                    for transport in transports:
                        local.extend(transport.iceGatherer.getLocalCandidates())
                        remote.extend(transport.getRemoteCandidates())
                    value['public_ice_candidates']={'available':True,'transport_count':len(transports),
                        'local':_candidate_counts(local),'remote':_candidate_counts(remote)}
                except Exception:
                    value['public_ice_candidates']={'available':False}
                try:
                    report=await asyncio.wait_for(self.peer.getStats(),timeout=0.25)
                    buckets={'dtls_srtp_transport_bytes_sent':[], 'dtls_srtp_transport_bytes_received':[],
                        'outbound_rtp_bytes_sent':[], 'inbound_rtp_bytes_received':[]}
                    for stat in report.values():
                        for typ,attr,key in [('transport','bytesSent','dtls_srtp_transport_bytes_sent'),
                            ('transport','bytesReceived','dtls_srtp_transport_bytes_received'),
                            ('outbound-rtp','bytesSent','outbound_rtp_bytes_sent'),
                            ('inbound-rtp','bytesReceived','inbound_rtp_bytes_received')]:
                            count=getattr(stat,attr,None)
                            if getattr(stat,'type',None)==typ and type(count) is int and count>=0:
                                buckets[key].append(count)
                    value['dtls_rtp_stats']={key:sum(counts) if counts else 'unknown' for key,counts in buckets.items()}
                except Exception:
                    value['dtls_rtp_stats']={'available':False}
                _LOG.info('RTC_MEDIA_DIAG_V1 %s',json.dumps(value,sort_keys=True,separators=(',',':')))
        except Exception:
            pass


_PROCESS_BUDGET=MediaDiagnosticBudget(os.environ.get('SCC_VOICE_MEDIA_DIAGNOSTIC_CALLS','0'))


def reserve_media_diagnostics(peer_factory):
    return _PROCESS_BUDGET.reserve_factory(peer_factory)
