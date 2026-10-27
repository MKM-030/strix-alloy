#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>
namespace hgn01816_hcmean_gpu {
constexpr std::uint32_t width=2560, streams=4, taps=5, concat_width=12800;
constexpr std::uint32_t completed_layers[taps]={5,15,25,35,45};
enum class Mode:std::uint32_t { Decode=1, Prefill=2 };
enum class Status:std::uint32_t { Ok, Mode, Rows, Tap, Stride, Capacity, Pointer, Overlap };
struct Job {
    const std::uint16_t* raw{};
    std::uint16_t* owned_output{};
    std::uint64_t raw_elements{}, output_elements{};
    std::uint64_t raw_row_stride{10240}, raw_stream_stride{2560};
    // 2560: separate mean; 12800: strided tap view of an owned concat allocation.
    std::uint64_t output_row_stride{12800};
    std::uint32_t full_rows{}, source_first{}, rows{}, destination_rows{}, destination_first{};
    std::uint32_t tap{}, completed_layer{};
    Mode mode{Mode::Decode};
};
inline Status validate(const Job& j) noexcept {
    if (j.mode!=Mode::Decode && j.mode!=Mode::Prefill)return Status::Mode;
    const auto max_rows=j.mode==Mode::Decode?4u:8192u;
    if (!j.full_rows || j.full_rows>max_rows || !j.rows || j.source_first>=j.full_rows ||
        j.rows>j.full_rows-j.source_first || !j.destination_rows || j.destination_rows>8192 ||
        j.destination_first>=j.destination_rows || j.rows>j.destination_rows-j.destination_first)return Status::Rows;
    if (j.tap>=taps || j.completed_layer!=completed_layers[j.tap])return Status::Tap;
    if (j.raw_stream_stride<width || j.raw_stream_stride>1048576 || j.raw_stream_stride%8 ||
        j.raw_row_stride<3*j.raw_stream_stride+width || j.raw_row_stride>4194304 || j.raw_row_stride%8 ||
        (j.output_row_stride!=width && j.output_row_stride!=concat_width))return Status::Stride;
    const std::uint64_t raw_end=(std::uint64_t(j.full_rows)-1)*j.raw_row_stride+3*j.raw_stream_stride+width;
    const std::uint64_t output_end=std::uint64_t(j.destination_rows)*j.output_row_stride;
    const auto max=std::numeric_limits<std::uintptr_t>::max();
    if (j.raw_elements<raw_end || j.output_elements<output_end || j.raw_elements>max/2 || j.output_elements>max/2)return Status::Capacity;
    auto a=reinterpret_cast<std::uintptr_t>(j.raw),b=reinterpret_cast<std::uintptr_t>(j.owned_output);
    if (!a || !b || a%16 || b%16 || a>max-j.raw_elements*2 || b>max-j.output_elements*2)return Status::Pointer;
    if (a<b+j.output_elements*2 && b<a+j.raw_elements*2)return Status::Overlap;
    return Status::Ok;
}
} // namespace hgn01816_hcmean_gpu
