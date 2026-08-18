#!/usr/bin/env bash
# ======================================================================
# check_gpu.sh — Identify every display/GPU card on this Ubuntu machine
# ----------------------------------------------------------------------
# Why: before assigning a card to the AI node (gpu01), you need to know
#   * which cards are physically present (PCI level — always works)
#   * whether an NVIDIA driver is loaded and which one
#   * the CUDA compute capability (sm_XX) — decides PyTorch/CUDA version
#
# Safe & read-only: this script only READS system info, changes nothing.
# Run:  bash check_gpu.sh
# ======================================================================

echo "=================================================================="
echo " GPU / DISPLAY CARD REPORT   ($(hostname) — $(date '+%Y-%m-%d %H:%M'))"
echo "=================================================================="

# ----------------------------------------------------------------------
# 1. PCI-level detection (ALWAYS works, no driver needed)
#    This is the ground truth: what hardware is physically plugged in.
# ----------------------------------------------------------------------
echo
echo "------ [1] Cards physically present (lspci) ----------------------"
if command -v lspci >/dev/null 2>&1; then
    # -nn shows vendor:device IDs too, useful for exact identification
    lspci -nn | grep -iE 'vga|3d|display' || echo "  (no VGA/3D/Display device found)"
else
    echo "  lspci not installed. Install with: sudo apt install pciutils"
fi

# ----------------------------------------------------------------------
# 2. Which kernel driver is bound to each card
#    Tells you if the card is actually USABLE (driver loaded) or just
#    sitting there unrecognised.
# ----------------------------------------------------------------------
echo
echo "------ [2] Kernel driver in use per card -------------------------"
if command -v lspci >/dev/null 2>&1; then
    lspci -k | grep -iEA3 'vga|3d|display' | grep -iE 'vga|3d|display|driver|kernel' \
        || echo "  (could not read driver binding)"
else
    echo "  lspci not available."
fi

# ----------------------------------------------------------------------
# 3. NVIDIA-specific details (only if an NVIDIA card + driver present)
#    nvidia-smi = the authoritative NVIDIA tool. If this works, the
#    driver is healthy and the GPU is ready for CUDA.
# ----------------------------------------------------------------------
echo
echo "------ [3] NVIDIA driver status (nvidia-smi) ---------------------"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap \
        --format=csv,noheader 2>/dev/null \
        && echo "  -> NVIDIA driver is loaded and working." \
        || nvidia-smi   # fall back to full output if the query flags fail
else
    echo "  nvidia-smi NOT found."
    echo "  Either: no NVIDIA card, OR the driver isn't installed yet."
    echo "  To install the recommended driver:  sudo ubuntu-drivers autoinstall"
fi

# ----------------------------------------------------------------------
# 4. Compute capability lookup (the number that decides PyTorch/CUDA)
#    sm_61 = Pascal (GTX 10-series) -> pin PyTorch 2.4.1 + CUDA 12.1
#    sm_75 = Turing (GTX 16 / RTX 20)   -> modern PyTorch OK
#    sm_86 = Ampere (RTX 30)            -> modern PyTorch OK
# ----------------------------------------------------------------------
echo
echo "------ [4] What the compute capability means ---------------------"
if command -v nvidia-smi >/dev/null 2>&1; then
    CC=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')
    if [ -n "$CC" ]; then
        echo "  Detected compute capability: $CC"
        case "$CC" in
            6.1) echo "  -> PASCAL (e.g. GTX 1050 Ti/1060/1070/1080). MODERN PyTorch DROPS this." ;
                 echo "     Pin: PyTorch 2.4.1 (cu121) + CUDA 12.1 + cuDNN <=9.11.1." ;;
            7.0|7.2) echo "  -> VOLTA. Still supported by recent PyTorch." ;;
            7.5) echo "  -> TURING (GTX 16 / RTX 20). Modern PyTorch works fine." ;;
            8.0|8.6|8.7|8.9) echo "  -> AMPERE/ADA (RTX 30/40). Latest PyTorch works great." ;;
            *) echo "  -> Look up this compute cap to pick the right PyTorch/CUDA." ;;
        esac
    else
        echo "  (compute_cap not reported — driver may be too old; try: nvidia-smi)"
    fi
else
    echo "  (skip — no NVIDIA driver yet)"
fi

# ----------------------------------------------------------------------
# 5. Quick PyTorch GPU check (only if a Python env with torch exists)
#    The real proof: can PyTorch actually SEE and USE the GPU?
# ----------------------------------------------------------------------
echo
echo "------ [5] PyTorch GPU visibility (if torch installed) -----------"
if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PYEOF' 2>/dev/null || echo "  (torch not installed in this python3 — skip for now)"
import torch
print(f"  torch version      : {torch.__version__}")
print(f"  CUDA available     : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  GPU name           : {torch.cuda.get_device_name(0)}")
    print(f"  arch list (build)  : {torch.cuda.get_arch_list()}")
    cc = torch.cuda.get_device_capability(0)
    print(f"  device capability  : sm_{cc[0]}{cc[1]}")
PYEOF
else
    echo "  python3 not found."
fi

echo
echo "=================================================================="
echo " Done. Section [1] always works; [3]-[5] need the NVIDIA driver."
echo "=================================================================="