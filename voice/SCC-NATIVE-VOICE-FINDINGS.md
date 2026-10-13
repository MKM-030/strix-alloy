# SCC: Native Voice – Befund und verbleibende Schnittstelle

Stand: 13.10.2026. Ziel: eigene gehostete Modelle im nativen ServiceNow-Voice-Erlebnis, einschließlich Assistant Designer Voice und Now Mobile. Diese Datei dokumentiert den Befund; sie enthält keine neue Implementierung.

## Status

- Der native Voice-Pfad ist für den Custom LLM Provider weiterhin blockiert. Der ursprüngliche Enum-Fehler ist nicht behoben.
- Der separate Sprachclient verwendet eigene ASR/TTS und den bestehenden ServiceNow-Dialog über Bot API/HaloGen. Er ist ein Custom-Fallback, kein Ersatz des nativen Voice-Runtimes.
- Die Prüfung hat die korrigierte externe Navigation aus ServiceNow und HTTP 200 bestätigt; die Gateway-Suite meldet 56 bestandene Tests. Navigation-Fix: `b8de643`; dokumentierte Windows-Abnahme: `024f5ed`.
- Damit sind weder eine native Voice-Integration noch die Mikrofon-/Audio-Abnahme am Telefon des Benutzers nachgewiesen. Letztere steht aus.
- Keine weiteren Custom-UI-Seiten, Tabellen oder Provider-Nachbildungen zur Umgehung der nativen Grenze hinzufügen.

## Belegte Konfigurationskette

Quellen: vorhandener Upload `upload/Pasted markdown(3).md` mit vollständigem `VoiceServiceConfigurationSNC`, Cache-Ausgabe `upload/Pasted text(10).txt` und aktuelle Leseprüfung auf der Instanz.

1. `_getLLMProvider()` liest `sn_aia.AIAOneExtendUtility.getDefaultProvider()`.
2. Es wählt die HTTP-Connection über zwei Fälle: Now-LLM-Alias oder LLM-Proxy-Alias für alle anderen Provider.
3. Es liefert `provider`, `connectionurl`, `geoRoutingEnabled` und `routing`. Der Custom-LLM-Transformer und dessen HaloGen-Endpunkt werden in dieser Methode nicht ausgewertet.
4. `_buildVoiceSystemConfig()` setzt den LLM-Block und ruft zuletzt `_applyCustomConfigExtensions()` auf.
5. Diese Methode verwendet `sn_voice_aia.VoiceServiceConfigExt.getCustomConfig(serviceId, config)`. Änderungen am Objekt und der ältere Rückgabe-/Merge-Vertrag werden unterstützt.
6. `refreshCacheAndFetchConfig()` speichert das Ergebnis im Voice-Cache.

Der bereits ausgelesene Cache enthielt gleichzeitig:

```json
{
  "provider": "1e163d62ff1a2210ed26ffffffffffca",
  "connectionurl": "https://llmproxy-prod-gateway"
}
```

Die Custom-ID erreicht somit die erzeugte Voice-Konfiguration; sie wird nicht zuvor durch einen falschen Anzeigenamen ersetzt. Die Connection bleibt der ServiceNow-LLM-Proxy, nicht HaloGen.

## Live geprüfter REST-Handler

- Record: `sys_ws_operation/2099c2baffa422102557ffffffffffee`, Feld `operation_script`.
- Route: `/api/sn_voice_aia/ai_voice_agent/voice_system_config`.
- Der Handler prüft Kaa-Authentifizierung und `serviceId`, ruft `new VoiceServiceConfiguration().getVoiceSystemConfig(serviceId, cacheDate, testMode)` auf und liefert bei Erfolg direkt `response.setBody(voiceSystemConfig)` mit Status 200.
- Im geprüften Handler gibt es keine Provider-Enum- oder Pydantic-Schemavalidierung.
- Die verwendete Klasse `sn_voice_aia.VoiceServiceConfiguration` erweitert unverändert `VoiceServiceConfigurationSNC`. Eine gleichnamige Klasse in `sn_nowassist_va` ist eine andere Klasse.

Die beobachtete Fehlermeldung stammt aus der nachgelagerten Validierung von `GlideResult[VoiceSystemConfig].result.llm.provider`. Der dortige Python-Vertrag lehnt die Custom-ID ab. Die genaue Version und Implementierung dieses externen Validators liegen uns nicht vor; der Instanz-Handler ist nachweislich nicht dessen Besitzer.

## Speech-Konfiguration und Grenze der Extension

- `_getSTTConfig()` liefert im vorhandenen Quellcode ein leeres Objekt.
- Der ausgelieferte TTS-Block enthält `voice_id`, `voice_gender` und sprachbezogene `voices`, keinen konfigurierten TTS-Endpunkt.
- `gatewayMode` und `orchestrationMode` werden aus Deployment-Attributen beziehungsweise Defaults übernommen. Ihre vollständigen Backend-Verträge sind nicht bekannt.
- Die Extension kann JSON verändern. Sie registriert dadurch keinen neuen Python-Enum-Wert, Provider-Adapter oder Speech-Transport im Voice-Dienst.
- Eine Änderung von `connectionurl` allein passiert die bekannte Provider-Validierung nicht. Ein unterstützter Providername oder eine leere Zeichenfolge darf nicht als angeblicher Custom-Modus ausgegeben werden.

## Entwurf einer Anfrage an ServiceNow – nicht gesendet

Auf Australia Patch 6w39 mit ServiceNow Otto for Voice Agents 6.0.5 wollen wir einen selbst gehosteten OpenAI-kompatiblen HaloGen-Endpunkt im nativen Assistant Designer Voice/Now-Mobile-Erlebnis verwenden. Custom Skills und der separate Bot-API-Pfad funktionieren bereits. Der native Voice-Dienst lehnt die Custom-Provider-ID bei `GlideResult[VoiceSystemConfig].result.llm.provider` ab, obwohl die Instanz sie mit HTTP 200 korrekt ausliefert.

Bitte bestätigen beziehungsweise bereitstellen:

1. Den für unsere Instanz tatsächlich eingesetzten Voice-Runtime-Build und dessen `VoiceSystemConfig`-/LLM-/STT-/TTS-Schema einschließlich erlaubter Provider- und Moduswerte.
2. Ob ein generischer, selbst gehosteter LLM-Adapter verfügbar oder aktivierbar ist; dessen Registrierung, Providerkennung und unterstützten `VoiceServiceConfigExt`-Vertrag.
3. Die Semantik von `llm.connectionurl`: interner Proxy oder frei konfigurierbarer Modell-Endpunkt; erforderliche Authentifizierung, Egress/TLS-Vorgaben, Modellname, Request-/Responseformat, Streaming und Tool-Calling.
4. Ob eigene ASR-/TTS-Endpunkte im nativen Runtime unterstützt werden; gegebenenfalls Transport, Audioformate, Streaming-/Turn-Taking-Vertrag, Voice-ID-Zuordnung und Authentifizierung.
5. Falls dafür eine Produktänderung erforderlich ist: den vorgesehenen Erweiterungs-/Freischaltungsweg. Wir möchten weder geschützte Basisklassen ändern noch einen anderen Provider vortäuschen.

## Abnahme eines späteren nativen Tests

Erst nach Klärung des tatsächlichen Adaptervertrags: eine Änderung auf genau einen Test-Voice-Assistenten begrenzen, vorherige Konfiguration sichern und den vorgesehenen Cache-Aktualisierungsweg verwenden. Keine globalen Provider-/Routing-Änderungen.

Bestanden ist der Test erst, wenn der native Assistant-Designer-Voice-Call ohne Enum-Fehler startet, korrelierte Requests den echten HaloGen-Endpunkt erreichen, ein vorhandenes Tool mit Benutzerbestätigung korrekt ausgeführt wird und eine hörbare Antwort zurückkommt. Eigene ASR/TTS müssen gesondert durch korrelierte Aufrufe nachgewiesen werden. Anschließend denselben Pfad im nativen Now-Mobile-Voice-Launcher testen. Ein Chat-Test oder eine eingebettete/externe Webseite genügt hierfür nicht.

## Öffentliche Primärquellen

- Native Voice und unterstützte LLMs: https://www.servicenow.com/docs/r/intelligent-experiences/deploy-ai-agents-for-voice.html
- Voice-Test über WebRTC, getrennt vom Chat-Test: https://www.servicenow.com/docs/r/zurich/conversational-interfaces/now-assist-in-virtual-agent/test-a-voice-assistant.html
- Native Mobile-Voice-Zuordnung: https://www.servicenow.com/docs/r/zurich/intelligent-experiences/integrate-voice-assistant-with-mobile-app-voice-launcher.html
- ServiceNow-Voice-Modellkarte mit Ink-Whisper/STT und Sonic-2/TTS: https://downloads.docs.servicenow.com/resource/enus/infocard/sn-voice.pdf
- ServiceNow-Mitarbeiter-FAQ, aktualisiert am 19.08.2026: eigener Voice-Orchestrator; Voice- und Chat-Agent-Runtimes sind noch getrennt: https://www.servicenow.com/community/servicenow-otto-articles/ai-voice-agents-are-here-autonomous-service-that-delights/ta-p/3448126

Die Quellen dokumentieren nicht den vollständigen privaten Voice-Runtime-Vertrag. Aus fehlender öffentlicher Dokumentation folgt keine technische Unmöglichkeit; genau dieser Vertrag muss für eine native Erweiterung geklärt werden.
