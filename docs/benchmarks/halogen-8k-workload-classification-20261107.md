# Frozen Halogen workload classification, 7 November 2026

The retained `historical8k` fixture contains synthetic prose assembled from
words and a story-writing instruction. The `natural16k` fixture contains a
contiguous excerpt from War and Peace followed by the same story instruction.
Each result applies to its exact frozen request and recorded configuration.

| Case | Actual input tokens | Request SHA256 | Input source |
| --- | ---: | --- | --- |
| `historical8k` | 8192 | `8a61749eed819c8d472c2705468369630f5dac9f6d606c897922d06e5bf4dba0` | Synthetic prose |
| `natural16k` | 16384 | `0d9cd3c7820d39ebb3c6f8ec4b712b8301e91d2eb2b97c52d9be678699ce6b3d` | Contiguous novel excerpt |

Earlier descriptions grouping both fixtures as natural text were inaccurate.
The archived response counts, output hashes and timings establish measurements
for the identified inputs. Comparing those rates with other engines requires
matching the workload construction as well as the sampler and runtime settings.

The retained private request directory is
`server/.local/halogen-update-20261025/primary01816/measurement-20261026T1903Z/plain-packet/`.
The 16K prompt consists of the first 66,336 novel characters, the frozen story
instruction and the original closed-thinking frame.

## New natural 8192-token preparation

A new case uses the first 33,025 characters from the same novel corpus. The
234-character story instruction and original chat frame give exactly 8192
tokens with the pinned tokenizer. Preparation searches character boundaries in
one contiguous prefix. Native response-usage verification is pending.

| Artifact | SHA256 |
| --- | --- |
| UTF-8 novel corpus | `353693ee8384aaba6ae2b78c75936bd668230d3cec8d7ac2c648351204bc1d23` |
| Tokenizer JSON | `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3` |
| New frozen request | `2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d` |

The offline counter also reproduced 16384 tokens for the existing novel request.
The new request and preparation receipt are retained under
`server/.local/halogen-update-20261107/primary0191/natural8192-prep/`.
