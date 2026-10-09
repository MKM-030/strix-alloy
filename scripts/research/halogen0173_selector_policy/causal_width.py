"""Project fixed depth from reviewed engine profile and exact copied Begin.

The qualified private cost reader joins causal_depth_low/high from unchanged v1
Begin events by exact begin_seq and owner. Raw stock_width=-1 stays unchanged.
Outcome attempted/accepted fields are never read in this projection.
"""


def project(row, profile):
    result = dict(row)
    if row.get("source") != "neural" or row.get("stock_width") != -1:
        return result
    if (profile.get("mtp_depth") == 2 and profile.get("spec_adapt") is False and
            row.get("causal_depth_low") == 2 and row.get("adaptive") == 0 and
            type(row.get("native_allowance")) is int and row["native_allowance"] >= 2):
        result.update(causal_stock_width=2, width_source="qualified_fixed_engine_profile_depth2")
    return result
