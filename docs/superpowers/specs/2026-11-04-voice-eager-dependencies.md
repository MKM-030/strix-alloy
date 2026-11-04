# Prepare selected conversation dependencies before serving calls

The first call after Native startup spent 5.210 seconds between final ASR and the Pipecat pipeline becoming ready. Existing logs identify the first-use dependency/setup boundary, but do not separately measure import and pre-link construction time. The pipeline's first link to ready took 16 ms. No claim that all 5.210 seconds are imports is made.

For a configured independent conversation transport, Native imports the validated optional adapter and existing socket/Pipecat classes during application startup, before HTTP resources and before serving callers. Preparation returns classes only. It creates no socket, client, pipeline, conversation, audio, inference request or business operation. Missing selected dependencies fail startup; legacy configuration retains its existing optional behavior.

Every actual call still owns its separate adapter, transport, Pipecat context, worker, call settings and epochs. Startup preparation and per-call import/setup durations are logged separately. All conversation guards and model/service selections remain unchanged. Root owns integration, manifest updates, reload and live qualification.
