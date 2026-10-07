# 0.17.1 private source adaptation

The previous 0.17.0 portable/source evidence is retained in the sealed reference.
This successor needs fresh source hashes and its own compiled/runtime pins.
The immutable image revision `9196bc6e7b20` and public release commit
`d4d3c1e24a83189666c1b65505dfc872dc00ebf7` have distinct provenance roles.
No 0.17.0 compiled/library/header qualification
is inherited. Agent-specific source adaptation receipts are stored beside this
package; their finite AST/source checks do not establish live compatibility.

Use native Windows PowerShell 5.1. Installation, activation, model reads, GPU/NPU
measurement and lifecycle work have not been performed. The production server
and its source pins remain unchanged. The new sources remain inactive.
