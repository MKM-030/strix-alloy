// Assembled offline for amdgcn-amd-amdhsa/gfx1151; sixteen approved H slots.
// This is an instruction fixture, not a launchable standalone kernel.
.text
.globl dpp_fixture
.type dpp_fixture,@function
dpp_fixture:
v_mov_b32_dpp v2, v21 row_xmask:8 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v4, v19 row_xmask:8 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v3, v20 row_xmask:8 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v1, v16 row_xmask:8 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v6, v2 row_xmask:4 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v8, v4 row_xmask:4 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v7, v3 row_xmask:4 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v8, v6 row_xmask:2 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v5, v1 row_xmask:4 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v1, v2 row_xmask:2 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v5, v3 row_xmask:2 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v11, v7 row_xmask:2 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v6, v4 row_xmask:1 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v2, v1 row_xmask:1 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v7, v5 row_xmask:1 row_mask:0xf bank_mask:0xf bound_ctrl:1
v_mov_b32_dpp v3, v0 row_xmask:1 row_mask:0xf bank_mask:0xf bound_ctrl:1
.size dpp_fixture,.-dpp_fixture
