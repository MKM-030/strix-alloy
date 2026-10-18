# Persönliche Zugänge und Stimmprofile löschen

Der bestehende Zugangscode aus `runtime/auth.json` bleibt unverändert der Administratorzugang. Der Administrator kann persönliche Zugänge anlegen. Jeder persönliche Zugang erhält eine stabile Identität und einen einmalig angezeigten, zufälligen Zugangscode. Gespeichert werden nur gesalzene PBKDF2-Verifikatoren in der privaten Datei `runtime/access-codes.json`.

Neue Aufnahmen gehören der angemeldeten Identität. Der Server schreibt die Eigentümerkennung in `owner.json`, bevor er das vollständige Profil atomar veröffentlicht. Eigentümerfelder aus Upload-Anfragen werden ignoriert. Vorhandene Profile ohne diese Kennung gehören dem Administrator. Alle angemeldeten Personen können gemeinsame Profile anhören; die Auswahl für den nächsten Anruf und synthetische Hörproben setzen zusätzlich die gültige Aufnahmefreigabe des Profils voraus.

## Zugang mit QR-Code erstellen

Nach der Administrator-Anmeldung steht der Bereich **Persönlichen Zugang erstellen** im aufklappbaren Administratorbereich neben **Abmelden**. Einen Namen eingeben und **Zugang mit QR-Code erstellen** wählen. Die Oberfläche zeigt den persönlichen Token, einen kopierbaren Anmeldelink und einen lokal erzeugten QR-Code. Ein Scan öffnet Voice Studio und meldet über den vorhandenen Login-Endpunkt an. Unter **Bereits angelegte Zugänge** bleiben Namen und Erstellungsdaten sichtbar; die Token können dort nicht erneut ausgelesen werden.

Der persönliche Token steht ausschließlich im URL-Fragment `#access=…`, das der Browser nicht als Teil des HTTP-Aufrufs überträgt. Die Anwendung entfernt es vor ihrer ersten API-Anfrage aus der Adresszeile und verwendet danach `POST api/login`. Nur persönliche Codes im Format `VSP-…` werden dafür angenommen; der Administratorcode wird nicht in einen Login-Link oder QR-Code umgewandelt. Ausblenden, Abmelden und Verlassen der Seite entfernen Token, Link und QR-Code aus der Oberfläche. Der QR-Encoder arbeitet ohne externen QR-Dienst; Lizenz und Herkunft sind in `web/vendor/qr-code.js` enthalten. `test-support/jsQR.cjs` dient ausschließlich dem unabhängigen Decodieren in Tests und wird nicht im Browser geladen.

`can_delete` bedeutet Berechtigung: eigener Zugang oder Administrator, mit Ausnahme der mitgelieferten Standardstimme. Eine ausgewählte Stimme bleibt gegen Löschen geschützt; dafür liefert der Server `409 selected_voice_protected`. Die Oberfläche kann den Löschknopf anzeigen, deaktivieren und zum vorherigen Auswählen einer anderen Stimme auffordern.

## HTTP-Vertrag

Alle schreibenden Anfragen benötigen die konfigurierte exakte HTTPS-Origin und `X-CSRF-Token`. Cookies bleiben Secure, HttpOnly und SameSite=Strict. Zugangscodes dürfen nicht in HTTP-URL-Pfade, Query-Parameter oder Protokolle geschrieben werden. Persönliche QR-Anmeldelinks verwenden ausschließlich das vor der ersten API-Anfrage entfernte URL-Fragment.

| Anfrage | Ergebnis |
| --- | --- |
| `POST api/login`, `{password}` | Bisherige Sitzungsfelder plus `principal_id`, `is_admin`, `label`. |
| `GET api/session` | Dieselben Identitätsfelder bei angemeldeter Sitzung. |
| `GET api/profiles` | Jedes Profil enthält zusätzlich `can_delete`, `can_activate` und `owner_is_self`; keine Eigentümerverifikatoren. |
| `GET api/access-codes` | Nur Administrator: `{access_codes:[{id,label,created_at_utc}]}`. |
| `POST api/access-codes`, `{label}` | Nur Administrator, Status 201: `{access_code:{id,label,created_at_utc},code}`. Der Code erscheint ausschließlich in dieser Antwort. |
| `DELETE api/profiles/{id}`, `{password}` | Bestätigung durch den Code der Sitzung oder den Administratorcode. Erfolgreiche endgültige Löschung: `{id,deleted:true}`. |

Ein anderer persönlicher Code bestätigt keine Löschung. Der Administratorcode kann als ausdrückliche Bestätigung auch innerhalb einer persönlichen Sitzung die Löschung einer fremden Aufnahme erlauben. Ausgewählte Stimmen, mitgelieferte Standardstimme und laufende Gespräche bleiben davon unabhängig geschützt.

## Editierbare Hörprobe je Stimmprofil

Neben **Original anhören** öffnet **Beispieltext anhören** einen Dialog mit dem gewählten Profil und einem längeren deutschen SCC-Begrüßungstext. Der Text lässt sich auf 3–300 Zeichen ändern und mit **Vorlesen** synthetisieren. Die Wiedergabe oben verwendet denselben Standardtext. Die Auswahl für den nächsten ServiceNow-Anruf bleibt unverändert.

`POST api/profiles/{id}/preview`, `{text}` benötigt Anmeldung, exakte Origin und CSRF und liefert WAV mit PCM16, mono, 24 kHz. Bei einem laufenden Native-Gespräch wird die Vorschau abgelehnt. Nach der Messe bleiben Hörproben der paketierten Standardstimme möglich. Abgelaufene Messeprofile bleiben für synthetische Hörproben gesperrt. Neue Profile sind nach dem verifizierten Kampagnenabschluss mit neuer eigener Stimm- und Aufbewahrungszustimmung wieder zulässig. Der Dialog räumt erzeugte Audio-URLs beim Schließen auf und spielt keine verspätete Antwort aus einem inzwischen geschlossenen Dialog ab.

Die TTS-Engine erhält unter den vorhandenen Sperren genau einen temporären internen Stimmnamen. Dieser wird nach der Synthese entfernt, ohne die registrierte ServiceNow-Stimme, Auswahl oder Registrierungsquittung zu ändern. Bei fehlgeschlagener Bereinigung antwortet der Server mit `503 preview_cleanup_failed`; eine private Datei `runtime/preview-cleanup.json` hält ausschließlich die interne temporäre Identität fest. Vor einer weiteren Vorschau und bei der Messe-Bereinigung wird diese Identität geprüft und bereinigt. Der Native-Status ist eine Vorabprüfung; ein während der Vorschau neu gestartetes Gespräch kann sich TTS-Kapazität mit der Vorschau teilen.

## Endgültige Löschung und Fehler

Der Server hält seine Stimmaktionssperre sowie die bestehende Betriebssystem-Sperre des Profilmanagers. Er prüft Eigentümer, Auswahl und sichere Pfade. Symlinks, Windows-Junctions und unerwartete Unterverzeichnisse werden abgelehnt. Anschließend verschiebt er genau die Aufnahme atomar in eine private Quarantäne und entfernt deren Dateien physisch, bevor er Erfolg meldet. Nach Erfolg gibt es keine verbleibende WAV-Kopie oder Löschjournaldatei.

Scheitert die physische Entfernung, antwortet der Server mit `503 delete_purge_failed`. Das Profil ist aus der Liste und den Audio-Endpunkten entfernt, mögliche Restdateien bleiben ausschließlich in der privaten Quarantäne. Ein Journal benennt genau diesen fehlgeschlagenen Vorgang. Der Administrator muss die Entfernung lokal abschließen; es gibt keinen allgemeinen Lösch-Endpunkt für solche Restdateien. Quarantäne und offene Journale sind auf acht Vorgänge begrenzt, Quarantäne zusätzlich auf 64 MiB. Bei voller Kapazität wird eine neue Löschung abgelehnt, bevor sie ihre Aufnahme verschiebt.

| Fehlercode | Bedeutung |
| --- | --- |
| `delete_confirmation_rejected` (403) | Eigener Zugangscode oder Administratorcode fehlt oder ist falsch. |
| `profile_delete_forbidden` (403) | Persönlicher Zugang besitzt dieses Profil nicht. |
| `profile_protected` (403) | Mitgelieferte Standardstimme. |
| `profile_unsafe_path` (403) | Pfad oder Dateityp ist für eine sichere Löschung ungeeignet. |
| `selected_voice_protected` (409) | Zuerst eine andere Stimme auswählen. |
| `call_in_progress` (409) | Nach dem laufenden Gespräch erneut versuchen. |
| `voice_operation_in_progress` (409) | Andere Auswahl, Vorschau oder Löschung läuft. |
| `delete_quarantine_full` (503) | Frühere fehlgeschlagene Entfernung muss geprüft werden. |
| `delete_purge_failed` (503) | Private Restdateien können noch bestehen; keine Erfolgsmeldung. |
| `delete_finalize_failed` (503) | Audio entfernt, Abschluss des internen Journals fehlgeschlagen. |

Die Prüfung laufender Gespräche verwendet den bestehenden Native-Health-Endpunkt. Sie ist keine atomare Reservierung neuer Telefonanrufe; die schon dokumentierte kleine Lücke zwischen Health-Prüfung und Stimmaktion bleibt bestehen. Diese Erweiterung ändert weder den Profilmanager noch Native Bridge, TTS, ASR oder Modellverwaltung.

## Automatische Löschung nach der Messe

Die unveränderte `retention-policy.json` legt das Ende der Messeaufbewahrung auf **16. Oktober 2026, 08:00 Uhr Europe/Berlin** (06:00 UTC) fest. Die Messeaufnahmen wurden entfernt. Der verifizierte Abschluss wird mit privatem Marker und gehashtem Bereinigungsbeleg festgehalten; der erfüllte Windows-Messe-Task ist deaktiviert. Ein gültiger Abschluss verhindert beim Studio-Start den erneuten Messe-Löschlauf und die damit verbundene Rücksetzung der TTS-Auswahl. Einzelheiten stehen in `RETENTION.md`.

Für jede neue Aufnahme verlangt das Portal neben der eigenen Stimmzustimmung eine gesonderte Bestätigung: **„Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.“** Beim Upload muss `consent` zusätzlich `retention: "until_deleted"` und diesen exakten `retention_notice` enthalten. Erstellungszeit und bestätigte Zustimmung müssen strikt nach der alten Messefrist liegen. Der Server prüft die Freigabe erneut unter der Betriebssystem-Sperre vor Veröffentlichung und unmittelbar vor der ersten nativen Stimmregistrierung. Alte Messezustimmungen werden nicht übernommen; abgelaufene Profile bleiben für Auswahl und synthetische Vorschau gesperrt.

`GET api/session` liefert `recording_allowed`, `postfair_mode` und den passenden `retention_notice`. Fehlende neue Zustimmung wird mit `400 postfair_consent_required` abgelehnt. Ohne gültigen lokalen Abschluss oder bei einem abgelaufenen Profil gilt weiterhin `409 fair_retention_expired`. Anmeldung, Lesen, berechtigtes Löschen und die Auswahl der paketierten Standardstimme bleiben möglich. Persönliche Zugänge und Administratorcode bleiben erhalten. Originalreferenzen unter `founder-test` sind keine Messekopien und wurden nicht entfernt. Der Weiterbetrieb stellt keine bereits gelöschten Profile wieder her und verspricht keinen neuen automatischen Löschtermin.
