"""This process on the performance cores (the user's call, 2026-11-16: "pin everything to performance").

While the game is in front the bot is a background console process, and Windows runs those on the efficiency
cores / throttled: the bench read 42-46 ms per tick so, 28.8-29.2 ms on the performance cores (same code).
`prefer_performance()` does three things to THIS process only (nothing about the game or any other process):
- affinity = the logical processors of the highest efficiency class (the P-cores; all of them when the CPU has
  one kind),
- priority class Above Normal,
- power throttling (EcoQoS) off.
Each step is best effort: a failure is reported in the returned line, never raised.
"""
import ctypes
import sys
from ctypes import wintypes

ABOVE_NORMAL_PRIORITY_CLASS = 0x8000
PROCESS_POWER_THROTTLING = 4                        # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1


class _CpuSet(ctypes.Structure):                    # SYSTEM_CPU_SET_INFORMATION (the CpuSet member)
    _fields_ = [("Size", wintypes.DWORD), ("Type", wintypes.DWORD), ("Id", wintypes.DWORD),
                ("Group", wintypes.WORD), ("LogicalProcessorIndex", ctypes.c_ubyte), ("CoreIndex", ctypes.c_ubyte),
                ("LastLevelCacheIndex", ctypes.c_ubyte), ("NumaNodeIndex", ctypes.c_ubyte),
                ("EfficiencyClass", ctypes.c_ubyte), ("AllFlags", ctypes.c_ubyte), ("Reserved", wintypes.DWORD),
                ("AllocationTag", ctypes.c_uint64)]


class _Throttling(ctypes.Structure):                # PROCESS_POWER_THROTTLING_STATE
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


def performance_mask(cpus: list) -> int:
    """Affinity mask of the processors with the highest efficiency class; `cpus` = [(index, class), ...]
    (processor group 0 only: an affinity mask cannot say more)."""
    if not cpus:
        return 0
    top = max(c for _, c in cpus)
    mask = 0
    for i, c in cpus:
        if c == top and i < 64:
            mask |= 1 << i
    return mask


def cpu_classes() -> list:
    """[(logical processor index, efficiency class)] of processor group 0 (GetSystemCpuSetInformation)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    need = wintypes.ULONG(0)
    k32.GetSystemCpuSetInformation(None, 0, ctypes.byref(need), None, 0)
    buf = ctypes.create_string_buffer(need.value)
    if not k32.GetSystemCpuSetInformation(buf, need.value, ctypes.byref(need), None, 0):
        return []
    out, off = [], 0
    while off < need.value:
        e = _CpuSet.from_buffer(buf, off)
        if e.Size == 0:
            break
        if e.Group == 0:
            out.append((int(e.LogicalProcessorIndex), int(e.EfficiencyClass)))
        off += e.Size
    return out


def prefer_performance() -> str:
    """Pin this process to the performance cores, Above Normal, unthrottled. Returns the log line."""
    if sys.platform != "win32":
        return "performance cores: not Windows, nothing done"
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    me = k32.GetCurrentProcess()
    said = []
    try:
        cpus = cpu_classes()
        mask = performance_mask(cpus)
        n = bin(mask).count("1")
        if mask and k32.SetProcessAffinityMask(me, mask):
            said.append(f"{n} of {len(cpus)} processors" + ("" if n < len(cpus) else " (one kind of core)"))
        else:
            said.append("affinity NOT set")
    except Exception as e:                           # noqa: BLE001 - best effort
        said.append(f"affinity NOT set ({e})")
    said.append("priority above normal" if k32.SetPriorityClass(me, ABOVE_NORMAL_PRIORITY_CLASS) else "priority NOT set")
    st = _Throttling(1, PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)          # control it, state off = never throttle
    ok = k32.SetProcessInformation(me, PROCESS_POWER_THROTTLING, ctypes.byref(st), ctypes.sizeof(st))
    said.append("no power throttling" if ok else "throttling NOT changed")
    return "performance cores: " + ", ".join(said)
