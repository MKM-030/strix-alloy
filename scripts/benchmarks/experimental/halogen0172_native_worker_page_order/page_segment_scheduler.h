// Private pure-CPU component. Does not launch threads, read files, change caches,
// compute IDs, publish native completion, or establish mapping ownership.
// prepare() is exclusive; the ready Schedule is immutable while workers copy
// disjoint page ranges. The owner must join every worker before reuse/destruction.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <span>
#include <stdexcept>
#include <vector>
namespace ple_page {
enum class Status { fallback, ready, complete, cancelled, invalid };
struct TableView { const std::byte* base{}; std::uint64_t row_count{}; const std::byte* mapping_base{}; std::size_t mapping_bytes{}; };
struct OutputView { std::byte* base{}; std::size_t capacity_bytes{}; };
// max_scratch_bytes bounds descriptor capacity of a ready plan. Warm/unselected
// calls leave reusable capacity untouched and perform no allocation/deallocation.
struct Policy { bool allow_page_order{}; std::size_t min_rows{4096}; std::size_t max_rows{131072}; std::size_t max_scratch_bytes{6*1024*1024}; };
struct Stop { void* cookie{}; bool (*requested)(void*) noexcept{}; };
class Schedule {
    // Source offset plus original destination byte offset. A segment never
    // spans source pages; sorting it cannot permute the native ID vector.
    struct Segment {
        std::uint64_t source_offset;
        std::uint32_t destination_row;
        std::uint16_t destination_byte;
        std::uint16_t bytes;
    };
    static_assert(sizeof(Segment)==16);
    static constexpr std::size_t row_bytes=160, page_bytes=4096, max_rows=131072;
    std::vector<Segment> segments_;
    std::vector<std::uint32_t> page_starts_;
    const std::byte* table_{};
    std::byte* output_{};
    bool ready_{};
    static bool stopping(Stop stop) noexcept { return stop.requested && stop.requested(stop.cookie); }
    static bool end_address(std::uintptr_t begin, std::size_t size, std::uintptr_t& end) noexcept {
        if (size>std::numeric_limits<std::uintptr_t>::max()-begin) return false;
        end=begin+size; return true;
    }
public:
    Status prepare(TableView table, OutputView output, std::span<const std::int64_t> ids,
                   Policy policy, Stop stop={}) noexcept {
        ready_=false;
        // Stock/warm path has no ID scan, scratch allocation, sort or barrier.
        if (!policy.allow_page_order || ids.size()<policy.min_rows || ids.empty()) return Status::fallback;
        if (stopping(stop)) return Status::cancelled;
        if (ids.size()>max_rows || ids.size()>policy.max_rows || !table.base || !table.mapping_base ||
            !output.base || !table.row_count || table.row_count>std::numeric_limits<std::size_t>::max()/row_bytes)
            return Status::fallback;
        const auto table_size=std::size_t(table.row_count)*row_bytes;
        const auto output_size=ids.size()*row_bytes; // ids.size() is already bounded.
        const auto mapping_begin=reinterpret_cast<std::uintptr_t>(table.mapping_base);
        const auto table_begin=reinterpret_cast<std::uintptr_t>(table.base);
        const auto output_begin=reinterpret_cast<std::uintptr_t>(output.base);
        const auto ids_begin=reinterpret_cast<std::uintptr_t>(ids.data());
        std::uintptr_t mapping_end, table_end, output_end, output_capacity_end, ids_end;
        if (!end_address(mapping_begin, table.mapping_bytes, mapping_end) ||
            !end_address(table_begin, table_size, table_end) || table_begin<mapping_begin || table_end>mapping_end ||
            output.capacity_bytes<output_size || !end_address(output_begin, output_size, output_end) ||
            !end_address(output_begin, output.capacity_bytes, output_capacity_end) ||
            !end_address(ids_begin, ids.size()*sizeof(std::int64_t), ids_end) ||
            (output_begin<mapping_end && mapping_begin<output_capacity_end) ||
            (output_begin<ids_end && ids_begin<output_end)) return Status::fallback;
        const auto segment_limit=ids.size()*2;
        const auto scratch_limit=segment_limit*sizeof(Segment)+(segment_limit+1)*sizeof(std::uint32_t);
        if (scratch_limit>policy.max_scratch_bytes) return Status::fallback;
        // Validate every ID before publishing readiness or modifying output.
        for (std::size_t row=0; row<ids.size(); ++row) {
            if ((row&255)==0 && stopping(stop)) return Status::cancelled;
            if (ids[row]<0 || std::uint64_t(ids[row])>=table.row_count) return Status::fallback;
        }
        try {
            if (scratch_bytes()>policy.max_scratch_bytes) {
                std::vector<Segment>().swap(segments_);
                std::vector<std::uint32_t>().swap(page_starts_);
            }
            segments_.clear(); page_starts_.clear();
            segments_.reserve(segment_limit); page_starts_.reserve(segment_limit+1);
            if (scratch_bytes()>policy.max_scratch_bytes) {
                std::vector<Segment>().swap(segments_);
                std::vector<std::uint32_t>().swap(page_starts_);
                return Status::fallback;
            }
            for (std::size_t row=0; row<ids.size(); ++row) {
                if ((row&255)==0 && stopping(stop)) return Status::cancelled;
                const auto source=std::uint64_t(ids[row])*row_bytes;
                const auto first=std::min(row_bytes, page_bytes-std::size_t((table_begin+source)%page_bytes));
                segments_.push_back({source, std::uint32_t(row), 0, std::uint16_t(first)});
                if (first<row_bytes)
                    segments_.push_back({source+first, std::uint32_t(row), std::uint16_t(first),
                                         std::uint16_t(row_bytes-first)});
            }
            std::sort(segments_.begin(), segments_.end(), [](const Segment& a, const Segment& b) noexcept {
                if (a.source_offset!=b.source_offset) return a.source_offset<b.source_offset;
                if (a.bytes!=b.bytes) return a.bytes<b.bytes;
                return a.destination_row<b.destination_row;
            });
            if (stopping(stop)) return Status::cancelled;
            for (std::size_t i=0; i<segments_.size(); ++i) {
                if ((i&255)==0 && stopping(stop)) return Status::cancelled;
                if (!i || (table_begin+segments_[i].source_offset)/page_bytes !=
                          (table_begin+segments_[i-1].source_offset)/page_bytes)
                    page_starts_.push_back(std::uint32_t(i));
            }
            page_starts_.push_back(std::uint32_t(segments_.size()));
        } catch (const std::bad_alloc&) { return Status::fallback; }
          catch (const std::length_error&) { return Status::fallback; }
        table_=table.base; output_=output.base;
        ready_=true;
        return Status::ready;
    }
    Status copy_pages(std::size_t first, std::size_t last, Stop stop={}) const noexcept {
        if (!ready_ || first>last || last>page_count()) return Status::invalid;
        if (stopping(stop)) return Status::cancelled;
        for (auto page=first; page<last; ++page) {
            if (stopping(stop)) return Status::cancelled;
            const Segment* primary=nullptr;
            for (auto i=page_starts_[page]; i<page_starts_[page+1]; ++i) {
                if ((i&63)==0 && stopping(stop)) return Status::cancelled;
                const auto& part=segments_[i];
                auto* destination=output_+std::size_t(part.destination_row)*row_bytes+part.destination_byte;
                if (primary && primary->source_offset==part.source_offset && primary->bytes==part.bytes) {
                    const auto* saved=output_+std::size_t(primary->destination_row)*row_bytes+primary->destination_byte;
                    std::memcpy(destination, saved, part.bytes);
                } else {
                    std::memcpy(destination, table_+part.source_offset, part.bytes);
                    primary=&part;
                }
            }
        }
        return Status::complete;
    }
    bool ready() const noexcept { return ready_; }
    std::size_t page_count() const noexcept { return ready_ ? page_starts_.size()-1 : 0; }
    std::size_t segment_count() const noexcept { return ready_ ? segments_.size() : 0; }
    // Descriptor capacity only; excludes vector objects and allocator bookkeeping.
    std::size_t scratch_bytes() const noexcept {
        const auto limit=std::numeric_limits<std::size_t>::max();
        if (segments_.capacity()>limit/sizeof(Segment) || page_starts_.capacity()>limit/sizeof(std::uint32_t))
            return limit;
        const auto segments=segments_.capacity()*sizeof(Segment);
        const auto starts=page_starts_.capacity()*sizeof(std::uint32_t);
        return starts>limit-segments ? limit : segments+starts;
    }
};
}
