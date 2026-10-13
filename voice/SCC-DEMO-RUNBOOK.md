# SCC-Demo: Laptop per eigener Stimme über den externen Sprachclient bestellen

Stand: 13. Oktober 2026. **Der Zugriffsfehler „Unzulässige Anfrage“ ist behoben:** Ein tatsächlicher Klick auf den ServiceNow-Button-Link öffnet jetzt erfolgreich die öffentliche Anmeldeseite. Die eigene Stimme ist über den externen SCC-Sprachclient angebunden. **Die native ServiceNow-Voice-Oberfläche ist weiterhin nicht mit dem Custom Provider verbunden.** Die Bedienung auf dem Vorführtelefon und ein weiterer neuer Gesprächsstart bleiben noch abzunehmen.

### Externer Sprachweg: bisheriger Nachweis

Ein technischer Sprachlauf mit automatischer Ausgabe von Namensfrage, Zusammenfassung und Bestellergebnis wurde erfolgreich geprüft. Er verwendete die bestehende Alex-Sommer-Bestellung **REQ0010012 / RITM0010011** erneut; der Dialog endete ohne Fehler. Die öffentliche Anmeldung ist nach der Zugriffskorrektur auch über einen tatsächlichen Link-Klick aus ServiceNow erreichbar. Die Now-Mobile-Quick-Action ist aktiv; sie öffnet eine externe HTTPS-Seite. Der Batch mit **120 Konfigurationsdatensätzen** ist abgeschlossen. Diese Nachweise ersetzen den noch ausstehenden Test mit Mikrofon und Wiedergabe auf dem Vorführtelefon nicht.

### Nativer ServiceNow-Sprachweg: noch nicht umgesetzt

Das ausdrückliche Ziel ist die Nutzung über die vorhandene ServiceNow-Oberfläche. **Der native Voice-Provider wurde durch die bisherige Umsetzung nicht ersetzt.** Für den Custom Provider ist derzeit kein nativer Anbindungspfad implementiert oder verifiziert. Die beobachtete native Provider-Validierung liegt in der Voice-Laufzeit; der gelesene ServiceNow-Handler gibt deren Konfiguration direkt zurück. Ein eigener LLM-Adapter- oder STT/TTS-Endpunktvertrag ist nicht nachgewiesen. Ein anderes Provider-Feld oder das Umstellen des Agenttyps allein löst diese Grenze nicht. Der angelegte Agent im Assistant Designer bleibt ein **Chat-Agent**. Die Befunde und nächsten Klärungsschritte stehen in `SCC-NATIVE-VOICE-FINDINGS.md`.

## Was gezeigt wird

Ein Vorgesetzter bestellt einen Laptop zum Onboarding. ServiceNow übernimmt Mitarbeitername, Eintrittsdatum, Vorgesetzten und Lieferort in eine normale Kataloganforderung mit REQ und RITM. Das Element **„SCC Laptop zum Onboarding (Demo)“** kostet 0 Euro. Es ist keine externe Beschaffungsintegration eingerichtet. Die vorhandene Standardverarbeitung erzeugt dennoch Katalogaufgaben; diese gehören zum Demo-Datensatz.

Der Einstieg ist **Now Mobile → Homepage → „SCC Laptop Voice“**. Mikrofonaufnahme und Sprachausgabe laufen im externen Browser, Dialog und Bestellung in ServiceNow.

| Aufgabe | Eingesetzte Komponente |
| --- | --- |
| Sprache erkennen | Lokales `Qwen/Qwen3-ASR-0.6B` |
| Dialog, Rückfragen und Tool-Auswahl | ServiceNow-Agent „SCC Laptop Onboarding“, vorhandenes `halogen-v2` |
| Bestellung | Standard-ServiceNow-Katalog über `sn_sc.CartJS` |
| Antwort sprechen | Lokales `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, eigenes Profil **SCC Demo** |
| Mobile Verbindung | HTTPS-Gateway → vorhandene Voice-Bridge → ServiceNow Bot-to-Bot |

**SCC Demo ist eine entworfene synthetische deutsche Stimme**, keine Kopie einer realen Person. Das größere VoiceDesign-Modell erzeugt einmalig die Referenz; zur Laufzeit wird das 0,6B-Base-Modell verwendet. Die Unterhaltung ist rundenbasiert: aufnehmen, senden, Antwort hören. Während der Antworterzeugung sind die Eingaben gesperrt; Full Duplex und Dazwischensprechen während der Generierung sind nicht vorgesehen. Sobald das Audio fertig erzeugt ist und abgespielt wird, kann eine neue Aufnahme die Wiedergabe stoppen.

## Vor dem Messeauftritt

1. Auf dem Rechner müssen HaloGen, ASR, TTS, Bridge, Gateway und Tailscale Funnel laufen. Der Rechner darf während der Demo nicht schlafen.
2. Ein Gerät und eine Unterhaltung gleichzeitig verwenden. Der Demo-Zugang arbeitet mit dem fest konfigurierten ServiceNow-Benutzer **Marcel KAEFKE**; es handelt sich nicht um eine Anmeldung jedes Besuchers an ServiceNow.
3. Den Zugang auf dem Vorführtelefon vorher testen: [SCC Laptop Voice öffnen](https://strix-alloy.tail7f425a.ts.net/scc-demo/). Das vorhandene Demo-Passwort wird ausschließlich auf der Anmeldeseite eingegeben. Es gehört nicht in Folien, QR-Codes oder diese Anleitung.
4. Mikrofonberechtigung erlauben. Eine kurze Aufnahme und „Erneut anhören“ prüfen; bei blockiertem automatischem Abspielen die Antwort ausdrücklich antippen.
5. Für jeden neuen Bestellnachweis einen anderen fiktiven Mitarbeiternamen verwenden. Identische Bestelldaten desselben Anforderers werden innerhalb des geprüften 24-Stunden-Fensters wiederverwendet.

**Latenz einplanen:** Im abschließenden vollständigen Sprachlauf benötigte die CPU-TTS etwa **12 Sekunden** für die Namensfrage (5,84 Sekunden Audio), **20 Sekunden** für die Zusammenfassung (9,60 Sekunden Audio) und **29 Sekunden** für die Ergebnisantwort (10,96 Sekunden Audio). Hinzu kommen Dialog- und ASR-Zeit. Die Agent-Anweisungen verwenden deshalb kurze gesprochene Antworten. Während „Bitte warten“ nicht mehrfach senden.

## Externen Sprachclient testen

Diese Bedienfolge beschreibt den externen Sprachclient. Für den reinen Skill-Test im Assistant Designer dieselben Sätze als Text eingeben; dort gibt es durch diese Umsetzung keine eigene Sprachausgabe.

1. **Now Mobile → Homepage → SCC Laptop Voice** öffnen, das Demo-Passwort eingeben und **„Anmelden & Gespräch starten“** wählen. Alternativ direkt die oben genannte HTTPS-Seite öffnen. Die Chat-Vorschau im Assistant Designer ist nicht der Sprachclient.
2. Bei einer bereits beendeten Unterhaltung „Neu starten“ wählen. Auf die Gesprächsbereitschaft warten, dann **„Sprechen“** wählen und sagen:

   > Mein neuer Mitarbeiter startet zum 1. November 2026. Sein Laptop soll zum Onboarding nach Hamburg in unsere Niederlassung geliefert werden.

   Danach **„Aufnahme stoppen“** wählen, den erkannten Text prüfen und **„Senden“** antippen. **„Text vor dem Senden prüfen“ ist standardmäßig aktiviert**; eine beendete Aufnahme wird deshalb nicht automatisch abgesendet. „1.11.“ ist ebenfalls der gewünschte Kurzbefehl. Für die wiederholbare Messevorführung ist **1. November 2026** eindeutig.
3. Auf die Rückfrage nach dem Namen antworten, zum Beispiel:

   > Der Mitarbeiter heißt Max Mustermann.

   Auch hier: **Sprechen → Aufnahme stoppen → Text prüfen → Senden**.

4. Die Zusammenfassung prüfen: Mitarbeitername, **1. November 2026**, **Hamburg**, **Marcel KAEFKE als Vorgesetzter**. Aus „mein neuer Mitarbeiter“ wird der angemeldete Anforderer als Vorgesetzter vorgeschlagen; diese Annahme muss in der Zusammenfassung sichtbar sein. Falls etwas falsch ist, vor der Bestellung korrigieren.
5. Erst danach ausdrücklich bestätigen:

   > Ja, bitte so bestellen.

   Die Bestätigung ebenfalls aufnehmen, prüfen und mit **„Senden“** abschicken.

6. Die Antwort muss eine reale Anforderungsnummer und Bestellpositionsnummer enthalten. In ServiceNow die RITM öffnen und die vier Variablen zeigen. Die zusätzlich erzeugten SCTASKs bleiben Demo-Aufgaben und sollen nicht als reale Lieferaufträge bearbeitet werden.

Bei einem unklaren Ergebnis oder Timeout zuerst die vorhandenen Anforderungen prüfen. Eine Bestellung nicht durch wiederholtes Senden erzwingen.

## Skills direkt in ServiceNow testen

1. [SCC Local Voice im Assistant Designer öffnen](https://soprasteriaassvsdemo14.service-now.com/now/conversational-studio/builder%3Ftable%3Dsys_now_assist_deployment%26sysId%3Dc623a20f93374354e7f2b9fa6aba10fd%26). Dieser Assistant ist **Chat-based**. Unter **Information sources → AI agents** ist **SCC Laptop Onboarding** als **Published / Active** eingetragen.
2. **„Test assistant“** wählen und als Text eingeben:

   > Mein neuer Mitarbeiter startet zum 1. November 2026. Sein Laptop soll zum Onboarding nach Hamburg in unsere Niederlassung geliefert werden.

3. Den Mitarbeiternamen beantworten, die vier Angaben in der Zusammenfassung prüfen und erst danach die Bestellung bestätigen. Für den Wiederverwendungsnachweis **Alex Sommer** mit denselben Angaben verwenden; für eine neue Demo-Bestellung einen neuen fiktiven Namen wählen.

Dieser Button prüft die ServiceNow-Skills und den Katalogdialog. **Die eigene Voice-Ausgabe ist nicht über „Test assistant“ angebunden.** Dafür den externen Sprachclient verwenden.

## Nachweis und noch offene Abnahme

| Prüfung | Stand |
| --- | --- |
| ServiceNow-Preview: Name → Zusammenfassung → Bestätigung → Bestellung | Erfolgreich: **REQ0010011 / RITM0010010** mit Max Mustermann, 2026-11-01, Hamburg und Marcel KAEFKE |
| Erneuter Tool-Aufruf mit identischen Daten | `reused:true`, dieselben IDs, keine zusätzliche Bestellung |
| Standard-Katalogaufgaben | RITM0010010 hat zwei SCTASKs: „Assess or Scope Task“ für **Field Services** und „Provide requested service“ für **Software** |
| Eigene TTS-Stimme → WAV → ASR | Erfolgreich; kurzer deutscher Prüfsatz mit exakt erkanntem Wortlaut |
| Öffentliches Gateway, Anmeldung und geschützte APIs | Fehler „Unzulässige Anfrage“ behoben; tatsächlicher Link-Klick aus ServiceNow öffnet die Anmeldung. 56 Tests bestanden: seitenübergreifende Link-Navigation HTTP 200, entsprechender API-Zugriff weiterhin 403, unangemeldete API 401, Einbettung im Frame 403. |
| Externe Gesprächsidentität | Eine neue externe Kennung funktionierte im ersten Gespräch. Beim zweiten Gespräch setzte die Plattform Konto und Adapter erneut auf den alten inaktiven Consumer zurück; eine dauerhafte Korrektur mit stabiler Kennung ist damit **nicht nachgewiesen**. |
| Sprach-Diagnoselauf bis echter Bestellung | Erfolgreich: gesprochenes Anliegen → ASR-Namensantwort **Alex Sommer** → Zusammenfassung → ASR-Bestätigung „Ja, bitte bestelle den Laptop.“ → **REQ0010012 / RITM0010011**; alle vier Variablen geprüft; Ergebnis über die eigene Stimme ausgegeben |
| Vollständiger Sprachlauf mit automatischen Rückfragen | **ERFOLGREICH** – Namensfrage, Zusammenfassung und Ergebnis wurden über den echten `/api/speak`-Pfad mit eigener Stimme ausgegeben. Die bestehende Alex-Sommer-Bestellung **REQ0010012 / RITM0010011** wurde wiederverwendet; `ended:true`, `failed:false`. Die InputText-/Picker-Korrektur ist zudem durch 53 Tests geprüft. |
| Unabhängige Prüfung nach dem Sprachlauf | Gespräch `b831519f93f34754e7f2b9fa6aba10d3` abgeschlossen, korrekter aktiver Consumer und Marcel als Benutzer. Weiterhin drei Demo-RITMs insgesamt, davon genau eine für Alex Sommer; keine zusätzliche Bestellung. |
| Weiteres neues Gespräch nach dem erfolgreichen Lauf | **Noch nicht abgenommen**; nachfolgender Benutzertest erforderlich. Sitzung wurde zurückgesetzt, abgemeldet und für den Test freigegeben. |
| Reales Vorführtelefon: Mikrofon, Safari/Browser-Audio, Now-Mobile-Einstieg | **Noch nicht auf dem tatsächlichen Vorführtelefon nachgewiesen**. |
| Native ServiceNow-Voice-Oberfläche mit Custom Provider | **Nicht umgesetzt und nicht nachgewiesen**. Der Designer-Agent ist weiterhin Chat; der vorhandene native Voice-Provider wird nicht ersetzt. |
| Now-Mobile-Quick-Action | **Aktiv** seit 13.10.2026, 07:32:33 UTC (09:32:33 Uhr Berlin); `active=1` nach dem Schreiben erneut gelesen. |
| Batch Update Set | **120/120 Konfigurationsdatensätze final erfasst und geprüft**, einschließlich Agent, Version und aktiver Mobile-Instanz. Haupt-Batch und alle drei Scope-Untersets sind **Complete**. |

## Betrieb und Wiederherstellung

Das Arbeitsverzeichnis auf Windows ist `C:\Projects\strix-alloy-scc-voice`. Diese geprüften Launcher zeigen den Status:

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-Voice.ps1' -Action Status
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-MobileVoice.ps1' -Action Status
```

Fehlende Dienste in dieser Reihenfolge starten; das Profil **SCC Demo** ist als Standard des Audio-Launchers hinterlegt:

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-Voice.ps1' -Action Start
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-MobileVoice.ps1' -Action Start
```

Bei einer verlorenen Sitzung Bridge und Gateway gemeinsam wiederherstellen:

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-MobileVoice.ps1' -Action Restart
```

Bridge und Gateway teilen einen einzelnen Sitzungskontext. Deshalb bei verlorener Sitzung beide gemeinsam neu starten; ein alleiniger Gateway-Neustart kann den einzigen Bridge-Platz belegt zurücklassen. `Start-MobileVoice.ps1 -Action Restart` lässt ASR, TTS, HaloGen und Funnel unverändert. `Start-Voice.ps1` unterstützt **keine** Aktion `Restart`. Die vorhandene HaloGen- und Funnel-Konfiguration beibehalten. Modell-Ladezeiten abwarten; keine zusätzlichen Worker auf bereits belegten Ports starten.

Für einen Rückbau zuerst die **SCC-Laptop-Voice-Button-Instanz deaktivieren** und nur den Funnel-Pfad `/scc-demo` entfernen. Die vorhandenen Pfade `/` und `/scc-voice` erhalten. Lokale Änderungen anhand der unten aufgeführten Commits gezielt zurücknehmen; keine pauschalen Prozessstopps, Verzeichnis-Resets oder Löschungen verwenden. Die vorherige TTS-Preset-Stimme lässt sich über den dokumentierten Ablauf in `voice/SYNTHETIC-VOICE.md` wiederherstellen. ServiceNow-Konfigurationsänderungen anhand ihrer vorherigen Versionen beziehungsweise des geprüften Update-Set-Verlaufs zurücknehmen. Bereits angelegte REQ/RITM sind Laufzeitdaten und werden dadurch nicht entfernt.

## Technischer Änderungsnachweis

| Bereich | Änderung / Datensatz |
| --- | --- |
| Katalogelement | `sc_cat_item / 401b878b93738354e7f2b9fa6aba102f`; vier Pflichtvariablen Mitarbeiter, Datum, Vorgesetzter, Lieferort; Preis 0, keine externe Beschaffungsintegration. Trotz leerer expliziter Flow-/Workflow-Zuordnung erzeugt die Standardverarbeitung zwei SCTASKs. |
| Hardware-Kategorie | `sc_cat_item_category / 13ab781b933f0754e7f2b9fa6aba10ba`; Zuordnung des Demo-Katalogelements zur vorhandenen Kategorie Hardware; im aktualisierten Batch erfasst |
| Agent | `sn_aia_agent / a4a9438393738354e7f2b9fa6aba101d`; „SCC Laptop Onboarding“ mit Kontext- und Bestelltool, Zusammenfassung und ausdrücklicher Bestätigung. Rolle und Anweisungen für kurze gesprochene Antworten ohne Markdown-Listen angepasst; Zusammenfassung mit vier Feldern und Bestätigungsfrage, Abschluss mit REQ/RITM und gegebenenfalls Wiederverwendung. Vorher-/Nachherstand in `scc-agent-voice-wording.json`. |
| Kontexttool | `sn_aia_tool / 15ebcb8f93738354e7f2b9fa6aba1072`; angemeldeten Anforderer und die benötigten Angaben liefern; versehentlich angehängtes leeres Standard-Skript entfernt |
| Bestelltool | `sn_aia_tool / 8b5c4f0393b38354e7f2b9fa6aba10f7`; geprüfter Warenkorb, Standard-REQ/RITM, Abgleich bestehender identischer Bestellungen; Bindungs-Postprocessor so korrigiert, dass Nummern im Agent-Ergebnis ankommen |
| ReAct-Kontext | `sys_generative_ai_config / 4780c7e193f747d0e7f2b9fa6aba1030`; Mission, Scratchpad, Gesprächsspeicher und Archiv über normale Prompt-Platzhalter ergänzt |
| HaloGen-Transformer | `sys_generative_ai_custom_llm_transformer / bc126377936f8750e7f2b9fa6aba1012`; `response_format: json_object` nur für obige ReAct-v3-Konfiguration; andere Skill-Formate bleiben erhalten |
| Vorzeitiger Gesprächsabbruch | `sys_script / a211df8f93378354e7f2b9fa6aba10da`; eigener Before-Insert-Business-Rule setzt nur bei SCC-Kontexten `u_resolution_required=false`, damit der vorhandene 90-Sekunden-CSM-Flow nicht startet; dieser Flow selbst blieb unverändert |
| Assistant und Channel | Deployment `c623a20f93374354e7f2b9fa6aba10fd`, Kontextprofil `c623e20f93374354e7f2b9fa6aba1081`, Bot-to-Bot-Channel `a40a3a0f93fb4354e7f2b9fa6aba1001`; sechs Profilmeldungen für die deutsche Demo angepasst |
| Now-Mobile-Einstieg | Button `b0e217cf93b78354e7f2b9fa6aba1028`, aktive Instanz `74e2df0393f78354e7f2b9fa6aba1000`, Zuordnung `78e2df0393f78354e7f2b9fa6aba1003`; Homepage-Quick-Action, Link `/scc-demo/`, externer Browser |
| Eigene Stimme | Profil `E:\SCC-Voice\voices\scc-demo`; portable Referenz und Manifest unter `voice/assets/scc-demo`; Commit `3a6676f` |
| Gateway und Produktionskorrekturen | `voice/mobile_gateway.py`, `voice/mobile_static/`, `voice/Start-MobileVoice.ps1`; Ausgangscommit `14ee605`, Dialogstart-Korrektur `0d39298`, Code-Commits `5665cea` und `f8025eb`; bereinigter Abnahmenachweis `d5e9362`. Zugriffskorrektur für die Link-Navigation `b8de643`, 56 Tests bestanden; tatsächlicher Navigationsnachweis im Acceptance-JSON mit Commit `024f5ed`. Zusatzdetails in `voice/MOBILE-GATEWAY-RECOVERY.md` |
| Gesprochene Rückfragen | InputText-/Picker-Rückfragen werden als Bot-Ereignisse für automatische TTS gespeichert; Korrektur mit 53 Tests einschließlich unabhängiger Prüfung und einem vollständigen Sprachlauf validiert. |
| Identität pro Gespräch | Optionaler Bridge-Schalter `session_scoped_user_id=true`, allgemeiner Standardwert `false`. Pro Unterhaltung eine undurchsichtige externe Kennung, während aller Nachrichten und beim Beenden unverändert; dieselbe fest konfigurierte authentifizierte E-Mail und derselbe ServiceNow-Benutzer. Vollständiger Sprachlauf erfolgreich; nächster Gesprächsstart noch zu prüfen. |
| TTS-Anbindung | Profilfähiger Audio-Service; Commit `0772075`; `Start-Voice.ps1` verwendet das persistierte SCC-Demo-Stimmprofil standardmäßig. |

Der Abgleich identischer Bestellungen schützt den Demo-Ablauf vor gewöhnlichen Wiederholungen. Er ist kein atomarer Schutz gegen parallele Bestellungen. Die Demo arbeitet deshalb mit einer Sitzung.

### Gesprächsidentität

Wiederverwendete externe Kennungen wurden beim nächsten Gespräch fälschlich auf einen alten inaktiven Consumer zurückgeführt. Die SCC-Konfiguration verwendet deshalb den optionalen Schalter `session_scoped_user_id=true`: eine neue undurchsichtige Kennung pro Unterhaltung, innerhalb aller Runden und beim Beenden unverändert. Authentifizierung, E-Mail und ServiceNow-Benutzer bleiben gleich. Dadurch entstehen zusätzliche Laufzeit-Zuordnungen; eine dialogübergreifende externe Historie unter einer Kennung entfällt. Der allgemeine Standardwert bleibt `false`.

Ein vollständiger Sprachlauf mit dieser Variante ist erfolgreich; der folgende neue Gesprächsstart bleibt abzunehmen. Manuelle Consumer-/Adapter-Korrekturen erwiesen sich als unwirksam und sind kein Installationsbestandteil. Die während der Diagnose kurz geänderte Gerätebedingung wurde wiederhergestellt. Benutzer und Rollen wurden nicht verändert; Laufzeit-Zuordnungen werden nicht transportiert.

### Batch Update Set

Name: **SCC 2026 - Local Voice + ITSM Laptop Demo - 2026-10-12**.

| Update Set | Sys-ID / Link |
| --- | --- |
| Haupt-Batch | [194a7413933f0754e7f2b9fa6aba1080](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=194a7413933f0754e7f2b9fa6aba1080) |
| Platform AI Agents and Skills | `514a7413933f0754e7f2b9fa6aba109c` |
| Generative AI Controller | `d54a7413933f0754e7f2b9fa6aba109e` |
| Global | `114a7413933f0754e7f2b9fa6aba10a0` |

Die finale Erfassung von **120/120 Datensätzen** wurde auf Datensatzidentität, Quell-/XML-Version und Anwendung geprüft; die Kontrolle auf unerwartete zusätzliche Update-Zeilen war erfolgreich. Die zuletzt geänderten Versionen von Agent, Agent-Version und aktiver Mobile-Instanz wurden erneut erfasst. Die Hardware-Kategorie-Zuordnung und das wiederhergestellte Kontextprofil sind enthalten. Anschließend wurden **Haupt-Batch und alle drei Untersets mit vier geprüften Schreibvorgängen auf Complete gesetzt**; Abschlussnachweis: `ok:true`, `status:complete`, `manifest_count:120`.

**Transportgrenzen:** Das Batch Update Set erfasst die zugehörige ServiceNow-Konfiguration nach tatsächlichem Scope. REQ/RITM, Dialogprotokolle, Consumer-/Client-Adapter-Laufzeitzuordnungen, lokale Python-Dienste, Modelle, Stimmen-Cache, Tailscale-Einrichtung und Zugangsdaten gehören nicht in dieses Update Set. Auf einer anderen Instanz müssen die benötigten ServiceNow-Apps, Benutzer/Rollen, vorhandenen Provider-/Modell-Konfigurationen sowie die geprüften Referenzen verfügbar sein; Zugangsdaten und Zieladressen werden dort separat eingerichtet. Das Paket ist ohne diese Voraussetzungen keine vollständige Installation.

**Verbleibende Arbeit und Abnahme:** Mikrofon und Wiedergabe auf dem Vorführtelefon sowie einen erneuten Gesprächsstart prüfen. Für das gewünschte native ServiceNow-Voice-Ziel zuerst den unterstützten Integrationsvertrag klären; die externe Webseite erfüllt diesen Teil des Ziels nicht. Der abgeschlossene Update-Set-Transport belegt die erfasste Konfiguration, nicht die Erfüllung dieses offenen Ziels. Weitere ServiceNow-Konfigurationsänderungen müssen zusätzlich nachvollziehbar erfasst werden.
