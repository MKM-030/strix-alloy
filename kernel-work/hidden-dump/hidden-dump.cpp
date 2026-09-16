// hidden-dump.cpp — dump the trunk's MTP input hidden states (`h_nextn`) for a corpus.
//
// WHY: the MTP draft head's accuracy is our decode bottleneck, and it currently ships
// pretrained for someone else's trunk/quant. Training a head fitted to OUR trunk needs
// teacher-forced pairs, and the head's input contract is defined in src/models/qwen4exp.cpp:
//
//   at position k the head consumes  (h[k-1] , embed(t_k))  and must predict  t_{k+1}
//
// where h is the trunk hidden *after* position k-1, at width n_embd_out = hc_mult * n_embd
// (the 4 hyper-connection streams). The fork already exposes exactly that tensor through
// llama_get_embeddings_nextn_ith(), so this tool is a thin, read-only dumper: no graph
// changes, no weights written, no product contact.
//
// OUTPUT
//   <out>.tokens   int32  [n_tokens]              token ids, in order
//   <out>.h        fp16   [n_tokens, n_embd_out]  trunk hidden after each position
//                  (--fp32  writes fp32 instead)
//   <out>.json     manifest: n_tokens, n_embd_out, dtype, window, model, harness revision
//
// The training pair at index k is then:
//   input  = (h[k-1], tokens[k])      (h[-1] = zeros at the start of each window)
//   target = tokens[k+1]
//
// Corpus is consumed in non-overlapping windows; the kv cache is cleared between windows so
// every window has full left context equal to its own length (this matches a fresh sequence
// at inference, which is what the head will see when drafting).
//
// usage:
//   llama-hidden-dump -m MODEL.gguf -f corpus.txt --out PREFIX --ntokens 65536 [--window 2048]
//                     [--fp32] [-c 2048] [-b 2048] [-ngl 999]

#include "arg.h"
#include "common.h"
#include "llama.h"
#include "src/llama-ext.h"   // llama_set_embeddings_nextn / llama_get_embeddings_nextn_ith

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

// ---- tiny fp32 -> fp16 (round-to-nearest-even) -------------------------------------------
static inline uint16_t f32_to_f16(float f) {
    uint32_t x;
    std::memcpy(&x, &f, sizeof(x));
    const uint32_t sign = (x >> 16) & 0x8000u;
    int32_t  exp  = (int32_t) ((x >> 23) & 0xffu) - 127 + 15;
    uint32_t mant = x & 0x7fffffu;

    if (((x >> 23) & 0xffu) == 0xffu) {            // inf / nan
        return (uint16_t) (sign | 0x7c00u | (mant ? 0x200u : 0u));
    }
    if (exp >= 0x1f) {                              // overflow -> inf
        return (uint16_t) (sign | 0x7c00u);
    }
    if (exp <= 0) {                                 // subnormal or zero
        if (exp < -10) { return (uint16_t) sign; }
        mant |= 0x800000u;
        const int shift = 14 - exp;
        uint32_t half = mant >> shift;
        // round to nearest even on the discarded bits
        const uint32_t rem = mant & ((1u << shift) - 1u);
        const uint32_t halfway = 1u << (shift - 1);
        if (rem > halfway || (rem == halfway && (half & 1u))) { half++; }
        return (uint16_t) (sign | half);
    }
    uint32_t half = ((uint32_t) exp << 10) | (mant >> 13);
    const uint32_t rem = mant & 0x1fffu;
    if (rem > 0x1000u || (rem == 0x1000u && (half & 1u))) { half++; }  // may carry into exp
    return (uint16_t) (sign | half);
}

static bool write_blob(const std::string & path, const void * data, size_t bytes, bool append) {
    FILE * f = std::fopen(path.c_str(), append ? "ab" : "wb");
    if (!f) {
        fprintf(stderr, "hidden-dump: cannot open '%s' for write\n", path.c_str());
        return false;
    }
    const size_t n = std::fwrite(data, 1, bytes, f);
    std::fclose(f);
    if (n != bytes) {
        fprintf(stderr, "hidden-dump: short write to '%s' (%zu/%zu)\n", path.c_str(), n, bytes);
        return false;
    }
    return true;
}

int main(int argc, char ** argv) {
    common_params params;
    params.n_ctx     = 4096;   // default window; overridable with -c

    // tool-local options, stripped before common_params_parse sees argv
    std::string out_prefix;
    int64_t     n_tokens_req = 0;
    int32_t     window       = 0;
    bool        want_fp32    = false;

    std::vector<char *> filtered;
    filtered.push_back(argv[0]);
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto take = [&](const char * name) -> const char * {
            if (i + 1 >= argc) { fprintf(stderr, "hidden-dump: %s needs a value\n", name); exit(2); }
            return argv[++i];
        };
        if (a == "--out")           { out_prefix   = take("--out"); }
        else if (a == "--ntokens")  { n_tokens_req = std::atoll(take("--ntokens")); }
        else if (a == "--window")   { window       = std::atoi (take("--window")); }
        else if (a == "--fp32")     { want_fp32    = true; }
        else                        { filtered.push_back(argv[i]); }
    }

    if (!common_params_parse((int) filtered.size(), filtered.data(), params, LLAMA_EXAMPLE_COMMON)) {
        return 1;
    }
    if (out_prefix.empty()) {
        fprintf(stderr, "hidden-dump: --out PREFIX is required\n");
        return 2;
    }
    if (params.prompt_file.empty()) {
        fprintf(stderr, "hidden-dump: -f CORPUS is required\n");
        return 2;
    }

    const int32_t n_batch = (int32_t) params.n_batch;
    const int32_t n_ctx   = (int32_t) params.n_ctx;
    if (window <= 0) { window = n_batch; }
    if (window > n_ctx) {
        fprintf(stderr, "hidden-dump: --window %d exceeds context %d\n", window, n_ctx);
        return 2;
    }
    if (n_tokens_req <= 0) { n_tokens_req = window; }
    n_tokens_req = (n_tokens_req / window) * window;   // whole windows only
    if (n_tokens_req <= 0) {
        fprintf(stderr, "hidden-dump: --ntokens must be >= one window (%d)\n", window);
        return 2;
    }

    common_init_result_ptr init = common_init_from_params(params);
    llama_model   * model = init->model();
    llama_context * ctx   = init->context();
    if (model == nullptr || ctx == nullptr) {
        fprintf(stderr, "hidden-dump: failed to load model\n");
        return 1;
    }

    const int32_t n_embd_out = llama_model_n_embd_out(model);
    if (n_embd_out <= 0) {
        fprintf(stderr, "hidden-dump: model has no nextn output width\n");
        return 1;
    }

    // The nextn hidden is produced for every token in the batch, and the unmasked copyback reads
    // n_tokens rows from it. Size the output buffers to the window so nothing is clipped: the
    // common_params defaults (n_outputs_max=0 -> n_batch, n_outputs_max_per_seq=1) otherwise size
    // them for a single row and the copyback reads past the allocation.
    params.n_outputs_max           = window;
    params.n_outputs_max_per_seq   = window;
    params.n_ubatch                = (params.n_ubatch > window) ? window : params.n_ubatch;

    // ---- read + tokenize the corpus -----------------------------------------------------
    std::string text;
    {
        FILE * f = std::fopen(params.prompt_file.c_str(), "rb");
        if (!f) { fprintf(stderr, "hidden-dump: cannot open corpus '%s'\n", params.prompt_file.c_str()); return 1; }
        // heap buffer, not a stack array: Windows' 1 MiB default stack reserve cannot hold a
        // 1 MiB frame, and the overflow fires at main() entry before any argument is read.
        std::vector<char> buf(1u << 18);
        size_t n;
        while ((n = std::fread(buf.data(), 1, buf.size(), f)) > 0) { text.append(buf.data(), n); }
        std::fclose(f);
    }
    std::vector<llama_token> toks = common_tokenize(ctx, text, /*add_special=*/ true, /*parse_special=*/ true);
    if ((int64_t) toks.size() < n_tokens_req) {
        fprintf(stderr, "hidden-dump: corpus has %zu tokens, need %lld\n", toks.size(), (long long) n_tokens_req);
        return 1;
    }
    toks.resize((size_t) n_tokens_req);

    fprintf(stderr, "hidden-dump: %lld tokens, n_embd_out=%d, window=%d, %s\n",
            (long long) n_tokens_req, n_embd_out, window, want_fp32 ? "fp32" : "fp16");

    // ---- open outputs ------------------------------------------------------------------
    const std::string f_tok = out_prefix + ".tokens";
    const std::string f_h   = out_prefix + ".h";
    if (!write_blob(f_tok, toks.data(), toks.size() * sizeof(int32_t), /*append=*/ false)) { return 1; }
    {   // truncate the hidden file so appends below start clean
        if (!write_blob(f_h, "", 0, /*append=*/ false)) { return 1; }
    }

    llama_set_embeddings_nextn(ctx, true, /*masked=*/ false);

    std::vector<float>   row_f32((size_t) n_embd_out);
    std::vector<uint16_t> row_f16((size_t) n_embd_out);

    llama_batch batch = llama_batch_init(window, 0, 1);

    const size_t bytes_done_report = 64u << 20;   // stderr progress every 64 MiB
    size_t h_bytes = 0, h_bytes_next_report = bytes_done_report;

    for (int64_t base = 0; base < n_tokens_req; base += window) {
        // fresh sequence: clear kv so this window's left context is exactly the window
        llama_memory_clear(llama_get_memory(ctx), /*data=*/ true);

        common_batch_clear(batch);
        for (int32_t i = 0; i < window; ++i) {
            // mark every token as an output: the nextn path computes h for all positions, and
            // inp_out_ids must select all of them or the hidden-copyback reads past the tensor
            common_batch_add(batch, toks[(size_t) base + i], i, { 0 }, /*logits=*/ true);
        }

        if (llama_decode(ctx, batch) != 0) {
            fprintf(stderr, "hidden-dump: llama_decode failed at token %lld\n", (long long) base);
            llama_batch_free(batch);
            return 1;
        }

        // unmasked nextn rows are dense by token position -> index i is position i
        std::vector<char> out;
        out.reserve((size_t) window * n_embd_out * (want_fp32 ? 4 : 2));
        for (int32_t i = 0; i < window; ++i) {
            const float * h = llama_get_embeddings_nextn_ith(ctx, i);
            if (!h) {
                fprintf(stderr, "hidden-dump: null nextn row at %lld\n", (long long) (base + i));
                llama_batch_free(batch);
                return 1;
            }
            if (want_fp32) {
                const char * p = (const char *) h;
                out.insert(out.end(), p, p + (size_t) n_embd_out * 4);
            } else {
                for (int32_t d = 0; d < n_embd_out; ++d) { row_f16[d] = f32_to_f16(h[d]); }
                const char * p = (const char *) row_f16.data();
                out.insert(out.end(), p, p + (size_t) n_embd_out * 2);
            }
        }
        if (!write_blob(f_h, out.data(), out.size(), /*append=*/ true)) {
            llama_batch_free(batch);
            return 1;
        }
        h_bytes += out.size();
        if (h_bytes >= h_bytes_next_report) {
            fprintf(stderr, "hidden-dump: %zu MiB written (%.1f%%)\n",
                    h_bytes >> 20, 100.0 * (double) (base + window) / (double) n_tokens_req);
            h_bytes_next_report += bytes_done_report;
        }
    }

    llama_batch_free(batch);
    // NOTE: do not free ctx/model here -- common_init_result_ptr owns both and frees them on
    // scope exit; a manual llama_free/llama_model_free produced a double-free teardown crash.

    // ---- manifest ----------------------------------------------------------------------
    {
        // backslashes must be escaped or the JSON is unparseable on Windows paths
        std::string corpus_esc;
        for (char c : params.prompt_file) {
            if (c == '\\' || c == '"') { corpus_esc += '\\'; }
            corpus_esc += c;
        }
        char buf[2048];
        std::snprintf(buf, sizeof(buf),
            "{\n"
            "  \"n_tokens\": %lld,\n"
            "  \"n_embd_out\": %d,\n"
            "  \"dtype\": \"%s\",\n"
            "  \"window\": %d,\n"
            "  \"corpus\": \"%s\",\n"
            "  \"contract\": \"input=(h[k-1], tokens[k]) -> target=tokens[k+1]; h[-1]=0 per window\"\n"
            "}\n",
            (long long) n_tokens_req, n_embd_out, want_fp32 ? "fp32" : "fp16",
            window, corpus_esc.c_str());
        if (!write_blob(out_prefix + ".json", buf, std::strlen(buf), /*append=*/ false)) { return 1; }
    }

    fprintf(stderr, "hidden-dump: wrote %s.{tokens,h,json}  (%zu MiB hidden)\n",
            out_prefix.c_str(), h_bytes >> 20);
    return 0;
}
