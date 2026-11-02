"""Shared offline authority fixture for existing real-loopback lifecycle tests."""
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.caller_binding import CallerBinding
from test_assistant_settings import SERVICE, AGENT

TOKEN = 'Bearer fixture.native.caller'


def configure_caller_authority(case, bridge):
    bridge.settings.caller_binding_service_id = SERVICE
    bridge.settings.caller_binding_agent_id = AGENT
    case.enterContext(patch('voice.bridge.resolve_native_caller',
        AsyncMock(return_value=CallerBinding('1'*32, 'fixture-caller@example.test'))))
    case.enterContext(patch('voice.bridge.refresh_native_caller_session', AsyncMock()))
