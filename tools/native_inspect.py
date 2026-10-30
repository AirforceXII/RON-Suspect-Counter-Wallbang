#!/usr/bin/env python3
"""Read-only PE function locator and bounded x64 disassembler for RON native names."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

DEFAULT_EXE = Path(
    r"F:\SteamLibrary\steamapps\common\Ready Or Not\ReadyOrNot\Binaries\Win64\ReadyOrNotSteam-Win64-Shipping.exe"
)
DEFAULT_CAPSTONE_DIR = Path(r"F:\Codex\2026-10-21\new-chat\work\native-deps")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = PROJECT_ROOT / "evidence" / "island-native-03" / "tool-results"


class InspectError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_capstone(capstone_dir: Path):
    try:
        import capstone  # type: ignore
    except ImportError:
        sys.path.insert(0, str(capstone_dir))
        try:
            import capstone  # type: ignore
        except ImportError as exc:
            raise InspectError(f"Capstone unavailable at {capstone_dir}: {exc}") from exc
    return capstone


class PEImage:
    def __init__(self, path: Path, data: bytes):
        self.path = path
        self.data = data
        if len(data) < 0x40 or data[:2] != b"MZ":
            raise InspectError("Input is not an MZ/PE image")
        pe_off = self.u32(0x3C)
        if pe_off + 24 > len(data) or data[pe_off : pe_off + 4] != b"PE\0\0":
            raise InspectError("Invalid PE signature or truncated COFF header")
        self.pe_off = pe_off
        coff = pe_off + 4
        self.machine = self.u16(coff)
        self.section_count = self.u16(coff + 2)
        optional_size = self.u16(coff + 16)
        self.optional_off = coff + 20
        if self.optional_off + optional_size > len(data):
            raise InspectError("Optional header extends past file")
        magic = self.u16(self.optional_off)
        if magic != 0x20B:
            raise InspectError(f"Expected PE32+ optional header, got 0x{magic:x}")
        if self.machine != 0x8664:
            raise InspectError(f"Expected AMD64 machine 0x8664, got 0x{self.machine:x}")
        self.image_base = self.u64(self.optional_off + 24)
        self.size_of_image = self.u32(self.optional_off + 56)
        self.size_of_headers = self.u32(self.optional_off + 60)
        directory_count = self.u32(self.optional_off + 108)
        self.directories_off = self.optional_off + 112
        if directory_count <= 3 or self.directories_off + 8 * (directory_count) > self.optional_off + optional_size:
            raise InspectError("PE optional header lacks the Exception directory")
        self.exception_rva, self.exception_size = struct.unpack_from(
            "<II", data, self.directories_off + 8 * 3
        )
        section_table = self.optional_off + optional_size
        if section_table + self.section_count * 40 > len(data):
            raise InspectError("Section table extends past file")
        self.sections: list[dict[str, Any]] = []
        for i in range(self.section_count):
            off = section_table + i * 40
            raw_name = data[off : off + 8].split(b"\0", 1)[0]
            name = raw_name.decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_off = struct.unpack_from("<IIII", data, off + 8)
            characteristics = self.u32(off + 36)
            self.sections.append(
                {
                    "name": name,
                    "virtual_size": virtual_size,
                    "virtual_address": virtual_address,
                    "raw_size": raw_size,
                    "raw_offset": raw_off,
                    "characteristics": characteristics,
                    "executable": bool(characteristics & 0x20000000),
                    "readable": bool(characteristics & 0x40000000),
                    "writable": bool(characteristics & 0x80000000),
                }
            )
        if not self.sections:
            raise InspectError("PE contains no sections")
        self.text_sections = [s for s in self.sections if s["name"] == ".text" and s["executable"]]
        if not self.text_sections:
            raise InspectError("No executable .text section found")
        if not self.exception_rva or not self.exception_size:
            raise InspectError("PE Exception data directory is empty")
        self._unwind_cache: dict[int, dict[str, Any]] = {}
        self.runtime_functions, self.pdata_report = self._read_runtime_functions()
        self.runtime_starts = [entry["begin_rva"] for entry in self.runtime_functions]

    def u16(self, off: int) -> int:
        return struct.unpack_from("<H", self.data, off)[0]

    def u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.data, off)[0]

    def u64(self, off: int) -> int:
        return struct.unpack_from("<Q", self.data, off)[0]

    def section_for_rva(self, rva: int, *, raw: bool = False) -> dict[str, Any] | None:
        for sec in self.sections:
            size = sec["raw_size"] if raw else max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + size:
                return sec
        return None

    def rva_to_off(self, rva: int) -> int | None:
        if rva < self.size_of_headers and rva < len(self.data):
            return rva
        sec = self.section_for_rva(rva, raw=True)
        if sec is None:
            return None
        off = sec["raw_offset"] + rva - sec["virtual_address"]
        if 0 <= off < len(self.data):
            return off
        return None

    def va_to_off(self, va: int) -> int | None:
        if va < self.image_base:
            return None
        return self.rva_to_off(va - self.image_base)

    def va_in_text(self, va: int) -> bool:
        if va < self.image_base:
            return False
        rva = va - self.image_base
        return any(
            sec["virtual_address"] <= rva < sec["virtual_address"] + max(sec["virtual_size"], sec["raw_size"])
            and self.rva_to_off(rva) is not None
            for sec in self.text_sections
        )

    def _read_runtime_functions(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        pdata_off = self.rva_to_off(self.exception_rva)
        if pdata_off is None or pdata_off + self.exception_size > len(self.data):
            raise InspectError("Exception directory does not map to complete file bytes")
        pdata_sec = self.section_for_rva(self.exception_rva, raw=True)
        if (
            pdata_sec is None
            or pdata_sec["name"] != ".pdata"
            or self.exception_rva + self.exception_size
            > pdata_sec["virtual_address"] + pdata_sec["raw_size"]
        ):
            raise InspectError("Exception directory is not fully contained by the raw .pdata section")
        count, remainder = divmod(self.exception_size, 12)
        entries: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        unsorted = 0
        overlaps = 0
        previous_begin = -1
        previous_end = -1
        for i in range(count):
            begin, end, unwind = struct.unpack_from("<III", self.data, pdata_off + i * 12)
            why = []
            if not begin or end <= begin:
                why.append("empty_or_reversed_range")
            if not self.va_in_text(self.image_base + begin) or not self.va_in_text(self.image_base + end - 1):
                why.append("range_outside_mapped_text")
            if self.rva_to_off(unwind) is None:
                why.append("unwind_info_unmapped")
            unwind_info = self.read_unwind_info(unwind)
            if not unwind_info["unwind_header_valid"]:
                why.append("unwind_info_header_unmapped_or_truncated")
            if begin < previous_begin:
                unsorted += 1
            if previous_end > begin:
                overlaps += 1
            previous_begin = begin
            previous_end = max(previous_end, end)
            record = {"begin_rva": begin, "end_rva": end, "unwind_rva": unwind, **unwind_info}
            if why:
                invalid.append({**record, "issues": why})
            else:
                entries.append(record)
        entries.sort(key=lambda item: (item["begin_rva"], item["end_rva"]))
        valid_overlaps = []
        for left, right in zip(entries, entries[1:]):
            if left["end_rva"] > right["begin_rva"]:
                valid_overlaps.append(
                    {"left": [left["begin_rva"], left["end_rva"]], "right": [right["begin_rva"], right["end_rva"]]}
                )
        report = {
            "directory_rva": hex(self.exception_rva),
            "directory_size": self.exception_size,
            "mapped_section": pdata_sec["name"] if pdata_sec else None,
            "record_size": 12,
            "records_total": count,
            "records_valid": len(entries),
            "records_invalid": len(invalid),
            "records_with_chaininfo": sum(1 for entry in entries if entry["unwind_chaininfo"]),
            "trailing_bytes": remainder,
            "source_order_inversions": unsorted,
            "overlapping_ranges": len(valid_overlaps),
            "invalid_samples": invalid[:20],
            "overlap_samples": valid_overlaps[:20],
            "validation_pass": bool(count and not invalid and not remainder and not unsorted and not valid_overlaps),
        }
        return entries, report

    def read_unwind_info(self, unwind_rva: int) -> dict[str, Any]:
        """Read an UNWIND_INFO header and, when present, its chained runtime record."""
        if unwind_rva in self._unwind_cache:
            return self._unwind_cache[unwind_rva]
        off = self.rva_to_off(unwind_rva)
        if off is None or off + 4 > len(self.data):
            result = {
                "unwind_header_valid": False,
                "unwind_version": None,
                "unwind_flags": None,
                "unwind_chaininfo": False,
                "chained_runtime_function": None,
            }
            self._unwind_cache[unwind_rva] = result
            return result
        version_flags, _prolog_size, count_or_payload_words, _frame = struct.unpack_from("<BBBB", self.data, off)
        version = version_flags & 0x07
        flags = (version_flags >> 3) & 0x1F
        chaininfo = bool(flags & 0x04)
        chained = None
        if chaininfo:
            # V1/V2 use CountOfCodes; V3 uses PayloadWords. Both place the
            # chained RUNTIME_FUNCTION at a DWORD-aligned offset after the header.
            payload_words = count_or_payload_words
            chain_off = off + 4 + ((payload_words * 2 + 3) & ~3)
            if chain_off + 12 <= len(self.data):
                chain_begin, chain_end, chain_unwind = struct.unpack_from("<III", self.data, chain_off)
                chained = {
                    "begin_rva": hex(chain_begin),
                    "end_rva": hex(chain_end),
                    "unwind_rva": hex(chain_unwind),
                    "mapped": bool(
                        chain_begin < chain_end
                        and self.va_in_text(self.image_base + chain_begin)
                        and self.va_in_text(self.image_base + chain_end - 1)
                        and self.rva_to_off(chain_unwind) is not None
                    ),
                }
        result = {
            "unwind_header_valid": True,
            "unwind_version": version,
            "unwind_flags": hex(flags),
            "unwind_chaininfo": chaininfo,
            "chained_runtime_function": chained,
        }
        self._unwind_cache[unwind_rva] = result
        return result

    def containing_runtime_function(self, va: int) -> dict[str, Any] | None:
        if va < self.image_base:
            return None
        rva = va - self.image_base
        i = bisect.bisect_right(self.runtime_starts, rva) - 1
        if i < 0:
            return None
        entry = self.runtime_functions[i]
        if entry["begin_rva"] <= rva < entry["end_rva"]:
            return entry
        return None

    def string_hits(self, name: str) -> list[dict[str, Any]]:
        hits = []
        variants = (("ascii", name.encode("ascii") + b"\0"), ("utf16le", name.encode("utf-16le") + b"\0\0"))
        for encoding, needle in variants:
            pos = 0
            while True:
                pos = self.data.find(needle, pos)
                if pos < 0:
                    break
                va = self.va_for_file_offset(pos)
                if va is not None:
                    hits.append({"encoding": encoding, "file_offset": pos, "string_va": va})
                pos += 1
        return sorted(hits, key=lambda x: (x["file_offset"], x["encoding"]))

    def va_for_file_offset(self, off: int) -> int | None:
        if off < 0 or off >= len(self.data):
            return None
        if off < self.size_of_headers:
            return self.image_base + off
        for sec in self.sections:
            if sec["raw_offset"] <= off < sec["raw_offset"] + sec["raw_size"]:
                return self.image_base + sec["virtual_address"] + off - sec["raw_offset"]
        return None

    def section_for_file_offset(self, off: int) -> str | None:
        for sec in self.sections:
            if sec["raw_offset"] <= off < sec["raw_offset"] + sec["raw_size"]:
                return sec["name"]
        return "headers" if 0 <= off < self.size_of_headers else None

    def string_at_va(self, va: int) -> str | None:
        off = self.va_to_off(va)
        if off is None:
            return None
        raw = self.data[off : off + 256]
        value = raw.split(b"\0", 1)[0]
        if len(value) >= 1 and all(32 <= byte < 127 for byte in value):
            return value.decode("ascii", errors="replace")
        return None

    def describe_function_params(self, va: int) -> dict[str, Any] | None:
        off = self.va_to_off(va)
        if off is None or off + 80 > len(self.data):
            return None
        owner = qword_at(self.data, off)
        name_ptr = qword_at(self.data, off + 16)
        repeated_owner = qword_at(self.data, off + 64)
        flags = qword_at(self.data, off + 56)
        rf_flags = struct.unpack_from("<I", self.data, off + 52)[0]
        if (
            owner is None
            or owner != repeated_owner
            or not self.va_in_text(owner)
            or name_ptr is None
            or not flags
        ):
            return None
        name = self.string_at_va(name_ptr)
        if not name:
            return None
        return {
            "params_va": hex(va),
            "function_name": name,
            "owner_constructor_va": hex(owner),
            "function_flags_offset_56": hex(flags & 0xFFFFFFFF),
            "rf_flags_offset_52": hex(rf_flags),
            "name_field_offset": 16,
            "function_flags_field_offset": 56,
        }


def qword_at(data: bytes, off: int) -> int | None:
    if off < 0 or off + 8 > len(data):
        return None
    return struct.unpack_from("<Q", data, off)[0]


def find_all(data: bytes, needle: bytes):
    start = 0
    while True:
        hit = data.find(needle, start)
        if hit < 0:
            return
        yield hit
        start = hit + 1


def collect_name_candidates(pe: PEImage, name: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    hits = pe.string_hits(name)
    candidate_map: dict[int, dict[str, Any]] = {}
    params_records: dict[int, dict[str, Any]] = {}
    for hit in hits:
        name_va = hit["string_va"]
        for ref_off in find_all(pe.data, struct.pack("<Q", name_va)):
            ref_sec = pe.section_for_file_offset(ref_off)
            if ref_sec in (None, ".text"):
                continue
            ref_va = pe.va_for_file_offset(ref_off)
            if ref_va is None:
                continue
            for delta in (-8, 8):
                slot_off = ref_off + delta
                code_va = qword_at(pe.data, slot_off)
                if code_va is None or not pe.va_in_text(code_va):
                    continue
                item = candidate_map.setdefault(
                    code_va,
                    {"candidate_va": code_va, "sources": []},
                )
                item["sources"].append(
                    {
                        "kind": "nameptr_neighbor",
                        "name_encoding": hit["encoding"],
                        "name_string_va": hex(name_va),
                        "name_pointer_slot_va": hex(ref_va),
                        "candidate_slot_delta_from_nameptr": delta,
                        "candidate_slot_va": hex(pe.va_for_file_offset(slot_off) or 0),
                        "reference_section": ref_sec,
                    }
                )
            struct_off = ref_off - 16
            if struct_off < 0 or struct_off + 80 > len(pe.data):
                continue
            owner_candidate = qword_at(pe.data, struct_off)
            repeated_candidate = qword_at(pe.data, struct_off + 64)
            stored_name = qword_at(pe.data, struct_off + 16)
            flags = qword_at(pe.data, struct_off + 56)
            rf_flags = struct.unpack_from("<I", pe.data, struct_off + 52)[0]
            if (
                owner_candidate is None
                or owner_candidate != repeated_candidate
                or stored_name != name_va
                or flags is None
                or not (flags & 0xFFFFFFFF)
                or not pe.va_in_text(owner_candidate)
            ):
                continue
            struct_va = pe.va_for_file_offset(struct_off)
            if struct_va is None:
                continue
            item = candidate_map.setdefault(owner_candidate, {"candidate_va": owner_candidate, "sources": []})
            raw80 = pe.data[struct_off : struct_off + 80]
            item["sources"].append(
                {
                    "kind": "FFunctionParams_Name_at_16_flags_at_56_candidate_at_0",
                    "layout_basis": "Name@16; RF flags@52; function flags@56; repeated code pointer@64",
                    "owner_constructor_va": hex(owner_candidate),
                    "name_encoding": hit["encoding"],
                    "name_string_va": hex(name_va),
                    "params_va": hex(struct_va),
                    "candidate_field_offset": 0,
                    "name_field_offset": 16,
                    "rf_flags_field_offset": 52,
                    "function_flags_field_offset": 56,
                    "rf_flags": hex(rf_flags),
                    "function_flags": hex(flags & 0xFFFFFFFF),
                    "raw_file": None,
                    "raw80_sha256": sha256(raw80),
                }
            )
            params_records[struct_off] = {
                "params_va": struct_va,
                "file_offset": struct_off,
                "raw": raw80,
                "name": name,
                "candidate_va": owner_candidate,
            }
    candidates = list(candidate_map.values())
    for item in candidates:
        item["sources"].sort(key=lambda x: (x["kind"], x.get("name_pointer_slot_va", x.get("params_va", ""))))
        boundary = pe.containing_runtime_function(item["candidate_va"])
        item["boundary_kind"] = "pdata" if boundary else "leaf_fallback"
        item["runtime_function"] = (
            {
                "start_va": hex(pe.image_base + boundary["begin_rva"]),
                "end_va": hex(pe.image_base + boundary["end_rva"]),
                "start_rva": hex(boundary["begin_rva"]),
                "end_rva": hex(boundary["end_rva"]),
            }
            if boundary
            else None
        )
    candidates.sort(key=lambda x: (min(s.get("name_pointer_slot_va", s.get("params_va", "0x0")) for s in x["sources"]), x["candidate_va"]))
    owner_records = []
    for item in candidates:
        for source in item["sources"]:
            if source["kind"].startswith("FFunctionParams_"):
                owner_records.append(
                    {
                        "params_va": source["params_va"],
                        "owner_constructor_va_candidate": source["owner_constructor_va"],
                        "function_flags_offset_56": source["function_flags"],
                        "rf_flags_offset_52": source["rf_flags"],
                    }
                )
    summary = {
        "name": name,
        "exact_string_hits": len(hits),
        "string_hits": [{**hit, "string_va": hex(hit["string_va"])} for hit in hits],
        "candidate_count": len(candidates),
        "function_params_owner_candidates": owner_records,
    }
    return summary, candidates, list(params_records.values())


def decode_readable_strings(raw: bytes) -> list[dict[str, str]]:
    strings = []
    narrow = raw.split(b"\0", 1)[0]
    if len(narrow) >= 4 and all(32 <= b < 127 for b in narrow):
        strings.append({"encoding": "ascii", "text": narrow[:120].decode("ascii", errors="replace")})
    even = len(raw) & ~1
    wide_raw = raw[:even]
    try:
        wide = wide_raw.decode("utf-16le", errors="strict").split("\0", 1)[0]
    except UnicodeDecodeError:
        wide = ""
    if len(wide) >= 4 and all(ch.isprintable() for ch in wide):
        item = {"encoding": "utf16le", "text": wide[:120]}
        if item not in strings:
            strings.append(item)
    return strings


def disassemble_candidate(
    pe: PEImage,
    capstone: Any,
    md: Any,
    candidate_va: int,
    max_bytes: int,
) -> dict[str, Any]:
    boundary = pe.containing_runtime_function(candidate_va)
    if boundary:
        start_rva = boundary["begin_rva"]
        end_rva = boundary["end_rva"]
        start_va = pe.image_base + start_rva
        start_off = pe.rva_to_off(start_rva)
        source = "pdata_runtime_function"
        available = max(0, end_rva - start_rva)
        scan_limit = min(available, max_bytes)
        boundary_end_va = pe.image_base + end_rva
    else:
        start_va = candidate_va
        start_off = pe.va_to_off(candidate_va)
        source = "leaf_candidate_fallback_from_address_until_terminal"
        sec = next(
            (
                s
                for s in pe.text_sections
                if pe.image_base + s["virtual_address"] <= candidate_va
                < pe.image_base + s["virtual_address"] + max(s["virtual_size"], s["raw_size"])
            ),
            None,
        )
        if sec is None or start_off is None:
            raise InspectError(f"Candidate VA {candidate_va:#x} has no .text file mapping")
        sec_end = sec["raw_offset"] + sec["raw_size"]
        available = max(0, sec_end - start_off)
        scan_limit = min(available, max_bytes)
        boundary_end_va = None
    if start_off is None or scan_limit <= 0:
        raise InspectError(f"Candidate VA {candidate_va:#x} has no readable bytes")
    raw = pe.data[start_off : start_off + scan_limit]
    raw_window = raw
    lines = []
    direct_calls = []
    direct_jumps = []
    rip_references = []
    decoded_size = 0
    terminated_by_ret = False
    leaf_terminator = None
    for ins in md.disasm(raw, start_va):
        decoded_size = ins.address + ins.size - start_va
        lines.append(
            {
                "address": hex(ins.address),
                "mnemonic": ins.mnemonic,
                "operands": ins.op_str,
            }
        )
        if ins.mnemonic in ("call", "jmp") and ins.operands:
            operand = ins.operands[0]
            if operand.type == capstone.x86.X86_OP_IMM:
                target = int(operand.imm) & 0xFFFFFFFFFFFFFFFF
                entry = {"instruction_va": hex(ins.address), "target_va": hex(target), "direct": True}
                (direct_calls if ins.mnemonic == "call" else direct_jumps).append(entry)
        for operand in ins.operands:
            if operand.type != capstone.x86.X86_OP_MEM or operand.mem.base != capstone.x86.X86_REG_RIP:
                continue
            target = ins.address + ins.size + operand.mem.disp
            target_off = pe.va_to_off(target)
            if target_off is None:
                continue
            strings = decode_readable_strings(pe.data[target_off : target_off + 160])
            ref = {
                "instruction_va": hex(ins.address),
                "target_va": hex(target),
                "target_section": pe.section_for_file_offset(target_off),
                "readable_strings": strings,
            }
            params = pe.describe_function_params(target)
            if params:
                ref["ffunction_params_candidate"] = params
            rip_references.append(ref)
        if source.startswith("leaf_") and ins.mnemonic in ("ret", "retf"):
            terminated_by_ret = True
            leaf_terminator = "ret"
            break
        if source.startswith("leaf_") and ins.mnemonic == "jmp" and ins.operands:
            operand = ins.operands[0]
            if operand.type == capstone.x86.X86_OP_IMM:
                target = int(operand.imm) & 0xFFFFFFFFFFFFFFFF
                # A direct jump outside the bounded candidate window ends this leaf
                # body (typically a tail call); local branch targets remain in scope.
                if target < start_va or target >= start_va + max_bytes:
                    leaf_terminator = "direct_tail_jump"
                    break
            elif operand.type in (capstone.x86.X86_OP_MEM, capstone.x86.X86_OP_REG):
                # An indirect unconditional jump ends this bounded leaf body. The
                # destination is unresolved statically, so do not decode into the
                # following function and label the boundary conservatively.
                leaf_terminator = "indirect_tail_jump"
                break
    if decoded_size == 0:
        raise InspectError(f"Capstone could not decode candidate VA {candidate_va:#x}")
    consumed = decoded_size
    raw = raw_window if boundary is not None else raw_window[:consumed]
    truncated = consumed >= max_bytes and (boundary is None and leaf_terminator is None or boundary is not None and available > max_bytes)
    if boundary is None and leaf_terminator is None:
        truncated = True
    return {
        "candidate_va": hex(candidate_va),
        "function_start_va": hex(start_va),
        "function_end_va": hex(boundary_end_va) if boundary_end_va is not None else hex(start_va + consumed),
        "function_size_bytes": consumed,
        "raw_bytes_length": len(raw),
        "decode_incomplete": consumed < scan_limit,
        "boundary_source": source,
        "pdata_boundary_present": bool(boundary),
        "runtime_function_fragment_only": True if boundary is not None else False,
        "unwind_version": boundary.get("unwind_version") if boundary else None,
        "unwind_flags": boundary.get("unwind_flags") if boundary else None,
        "unwind_chaininfo": boundary.get("unwind_chaininfo") if boundary else None,
        "chained_runtime_function": boundary.get("chained_runtime_function") if boundary else None,
        "leaf_terminated_by_ret": terminated_by_ret if boundary is None else None,
        "leaf_terminator": leaf_terminator if boundary is None else None,
        "truncated": truncated,
        "raw_bytes_hex": raw.hex(),
        "raw_bytes": raw,
        "instructions": lines,
        "direct_calls": direct_calls,
        "direct_jumps": direct_jumps,
        "rip_string_references": rip_references,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only PE/.pdata/native name locator and bounded x64 disassembler."
    )
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE, help="input PE executable; read-only")
    parser.add_argument("--capstone-dir", type=Path, default=DEFAULT_CAPSTONE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--output", default="native-inspect-results.json", help="JSON filename within --out-dir")
    parser.add_argument("--names", nargs="+", default=[], help="exact native names to locate")
    parser.add_argument("--addresses", nargs="+", default=[], help="VA values to inspect, e.g. 0x1447cd220")
    parser.add_argument("--max-functions", type=int, default=48, help="maximum disassemblies (hard limit 64)")
    parser.add_argument("--max-bytes", type=int, default=1024, help="bytes per function (hard limit 4096)")
    args = parser.parse_args(argv)
    if not args.names and not args.addresses:
        parser.error("provide --names and/or --addresses")
    if args.max_functions < 1 or args.max_functions > 64:
        parser.error("--max-functions must be 1..64")
    if args.max_bytes < 16 or args.max_bytes > 4096:
        parser.error("--max-bytes must be 16..4096")
    if Path(args.output).name != args.output:
        parser.error("--output must be a filename, not a path")
    try:
        args.address_values = [int(value, 0) for value in args.addresses]
    except ValueError as exc:
        parser.error(f"invalid --addresses value: {exc}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    exe_path = args.exe.resolve()
    if not exe_path.is_file():
        raise InspectError(f"Input executable not found: {exe_path}")
    data = exe_path.read_bytes()
    pe = PEImage(exe_path, data)
    capstone = load_capstone(args.capstone_dir.resolve())
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    name_reports = []
    candidate_groups: list[tuple[str, list[dict[str, Any]]]] = []
    params_records: dict[int, dict[str, Any]] = {}
    for name in args.names:
        try:
            name.encode("ascii")
        except UnicodeEncodeError as exc:
            raise InspectError(f"Native name must be ASCII: {name}") from exc
        summary, candidates, params = collect_name_candidates(pe, name)
        name_reports.append(summary)
        candidate_groups.append((name, candidates))
        for record in params:
            params_records[record["file_offset"]] = record

    requested_addresses = []
    for addr in args.address_values:
        if not pe.va_in_text(addr):
            raise InspectError(f"Requested VA {addr:#x} is not mapped executable .text")
        candidate_groups.append((f"address:{addr:#x}", [{"candidate_va": addr, "sources": [{"kind": "explicit_address"}], "boundary_kind": "pdata" if pe.containing_runtime_function(addr) else "leaf_fallback"}]))
        requested_addresses.append(hex(addr))

    # Round-robin candidate selection keeps all requested names represented under the hard cap.
    ordered: list[dict[str, Any]] = []
    indexes = [0] * len(candidate_groups)
    while len(ordered) < args.max_functions:
        made_progress = False
        for group_index, (label, group) in enumerate(candidate_groups):
            if len(ordered) >= args.max_functions:
                break
            while indexes[group_index] < len(group):
                candidate = group[indexes[group_index]]
                indexes[group_index] += 1
                key_boundary = pe.containing_runtime_function(candidate["candidate_va"])
                key = key_boundary["begin_rva"] if key_boundary else candidate["candidate_va"] - pe.image_base
                if any(existing["dedupe_key"] == key for existing in ordered):
                    # Keep provenance even when another requested name resolves to the same function.
                    for existing in ordered:
                        if existing["dedupe_key"] == key:
                            existing["candidate_records"].append({"query": label, **candidate})
                            break
                    continue
                ordered.append(
                    {
                        "dedupe_key": key,
                        "query_labels": [label],
                        "candidate_records": [{"query": label, **candidate}],
                        "candidate_va": candidate["candidate_va"],
                    }
                )
                made_progress = True
                if len(ordered) >= args.max_functions:
                    break
                break
        if not made_progress:
            break

    for group_index, (label, group) in enumerate(candidate_groups):
        for candidate in group[indexes[group_index] :]:
            boundary = pe.containing_runtime_function(candidate["candidate_va"])
            key = boundary["begin_rva"] if boundary else candidate["candidate_va"] - pe.image_base
            if any(existing["dedupe_key"] == key for existing in ordered):
                for existing in ordered:
                    if existing["dedupe_key"] == key:
                        existing["candidate_records"].append({"query": label, **candidate})
                        break

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for struct_off, record in params_records.items():
        label = record["name"].replace("/", "_")
        raw_name = f"params_{label}_{record['params_va']:016x}.bin"
        raw_path = raw_dir / raw_name
        raw_path.write_bytes(record["raw"])
        raw_relative = f"raw/{raw_name}"
        for name_report in name_reports:
            if name_report["name"] == record["name"]:
                for owner_record in name_report["function_params_owner_candidates"]:
                    if owner_record["params_va"] == hex(record["params_va"]):
                        owner_record["raw_file"] = raw_relative
                        owner_record["raw80_sha256"] = sha256(record["raw"])
        for group_name, group in candidate_groups:
            if group_name == record["name"]:
                for candidate in group:
                    if candidate["candidate_va"] == record["candidate_va"]:
                        for source in candidate["sources"]:
                            if source.get("params_va") == hex(record["params_va"]):
                                source["raw_file"] = raw_relative
                                source["raw80_hex"] = record["raw"].hex()

    functions = []
    for index, selected in enumerate(ordered, 1):
        try:
            fn = disassemble_candidate(pe, capstone, md, selected["candidate_va"], args.max_bytes)
        except InspectError as exc:
            fn = {
                "candidate_va": hex(selected["candidate_va"]),
                "disassembly_error": str(exc),
                "truncated": True,
            }
        raw = fn.pop("raw_bytes", b"")
        raw_name = f"fn_{index:02d}_{selected['candidate_va']:016x}.bin"
        if raw:
            raw_path = raw_dir / raw_name
            raw_path.write_bytes(raw)
            fn["raw_file"] = f"raw/{raw_name}"
            fn["raw_sha256"] = sha256(raw)
        fn["candidate_records"] = selected["candidate_records"]
        fn["query_labels"] = selected["query_labels"]
        fn["classifications"] = [
            "static_candidate_only",
            "registration_or_neighbor_pointer_does_not_prove_execution",
            "direct_call_target_does_not_prove_semantic_role",
        ]
        functions.append(fn)

    owner_metadata_by_name = {
        report["name"]: report.get("function_params_owner_candidates", []) for report in name_reports
    }
    for fn in functions:
        name_links = []
        for label in fn["query_labels"]:
            if label in owner_metadata_by_name and owner_metadata_by_name[label]:
                name_links.append(
                    {
                        "queried_name": label,
                        "owner_records_are_name_level_candidates_not_a_candidate_to_owner_proof": True,
                        "function_params_owner_candidates": owner_metadata_by_name[label],
                    }
                )
        fn["function_name_owner_context"] = name_links

    selection_status = []
    for group_index, (label, group) in enumerate(candidate_groups):
        total_unique = len(group)
        represented = sum(1 for fn in functions if label in fn["query_labels"])
        selection_status.append(
            {"query": label, "candidate_addresses": total_unique, "disassemblies_selected": represented, "selection_limited": represented < total_unique}
        )

    result = {
        "tool": "NativeInspect read-only PE locator/disassembler",
        "classification": "static candidate analysis only; no game code execution, process access, or asset writes",
        "input": {
            "exe": str(exe_path),
            "exe_sha256": sha256(data),
            "file_size": len(data),
            "capstone_version": capstone.__version__,
            "capstone_module": str(Path(capstone.__file__).resolve()),
            "python": sys.executable,
        },
        "reproducibility": {
            "argv": [str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)],
            "names_requested": args.names,
            "addresses_requested": requested_addresses,
            "max_functions": args.max_functions,
            "max_bytes_per_function": args.max_bytes,
        },
        "pe": {
            "machine": hex(pe.machine),
            "image_base": hex(pe.image_base),
            "size_of_image": hex(pe.size_of_image),
            "exception_directory": pe.pdata_report,
            "sections": [
                {
                    **sec,
                    "virtual_address": hex(sec["virtual_address"]),
                    "raw_offset": hex(sec["raw_offset"]),
                    "virtual_end": hex(sec["virtual_address"] + max(sec["virtual_size"], sec["raw_size"])),
                }
                for sec in pe.sections
            ],
        },
        "name_search": name_reports,
        "selection": selection_status,
        "functions": functions,
        "evidence_limit": "A .pdata Runtime Function record is an unwind extent/fragment, not a proven complete source-level function; chained unwind records are exposed where present. A name string, pointer neighbor, FFunctionParams layout, or static call target is not proof the game executes that path.",
    }
    out_path = args.out_dir / args.output
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"exe_sha256={result['input']['exe_sha256']}")
    print(f"image_base={hex(pe.image_base)} .pdata_valid={pe.pdata_report['records_valid']} invalid={pe.pdata_report['records_invalid']} pass={pe.pdata_report['validation_pass']}")
    print(f"functions={len(functions)} output={out_path}")
    for fn in functions:
        calls = ",".join(x["target_va"] for x in fn.get("direct_calls", []))
        jumps = ",".join(x["target_va"] for x in fn.get("direct_jumps", []))
        print(
            f"{fn.get('candidate_va')} start={fn.get('function_start_va')} boundary={fn.get('boundary_source')} "
            f"truncated={fn.get('truncated')} calls=[{calls}] jumps=[{jumps}]"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InspectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
