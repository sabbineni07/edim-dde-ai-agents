"""Subset of Databricks-efficiency allow-list for SKU validation."""

from typing import Optional, Set

# Ported subset from copilot databricks-efficiency SKILL (extend as needed)
ALLOWED_AZURE_NODE_TYPES: Set[str] = {
    "Standard_D2ds_v6",
    "Standard_D2ads_v6",
    "Standard_D4ds_v5",
    "Standard_D4ads_v6",
    "Standard_D4ads_v5",
    "Standard_D4s_v5",
    "Standard_D4ds_v6",
    "Standard_D8ads_v6",
    "Standard_D8ds_v5",
    "Standard_D8ds_v6",
    "Standard_D8ads_v5",
    "Standard_D16ads_v6",
    "Standard_D16ds_v6",
    "Standard_D16ds_v5",
    "Standard_E2ads_v6",
    "Standard_E2ds_v6",
    "Standard_E4ds_v5",
    "Standard_E4s_v5",
    "Standard_E4ads_v5",
    "Standard_E4ads_v6",
    "Standard_E4ds_v6",
    "Standard_E8ads_v6",
    "Standard_E8ds_v5",
    "Standard_E8ads_v5",
    "Standard_E8ds_v6",
    "Standard_E8s_v5",
    "Standard_E16ds_v5",
    "Standard_E16ads_v6",
    "Standard_E16ds_v6",
    "Standard_F4s_v2",
    "Standard_F8s_v2",
    "Standard_F16s_v2",
}


def compose_node_type(node_family: str, vcpus: int, generation: str = "v3") -> str:
    """Build Standard_{Family}{vcpus}s_{gen} — may not be on allow-list."""
    family = str(node_family).strip().upper()[:1]
    if family not in ("D", "E", "F", "L"):
        family = "E"
    v = max(4, int(vcpus))  # skill minimum 4 vcpus
    gen = generation if generation.startswith("v") else f"v{generation}"
    return f"Standard_{family}{v}s_{gen}"


def nearest_allowed_node_type(
    node_family: str,
    vcpus: int,
    current_node_type: Optional[str] = None,
) -> str:
    """Pick allow-listed SKU matching family and vCPU size intent."""
    family = str(node_family).strip().upper()[:1]
    v = max(4, int(vcpus))
    if current_node_type and current_node_type in ALLOWED_AZURE_NODE_TYPES:
        cur_f = current_node_type[9:10].upper() if len(current_node_type) > 9 else ""
        if cur_f == family:
            return current_node_type

    candidates = [
        n
        for n in ALLOWED_AZURE_NODE_TYPES
        if f"Standard_{family}" in n
        and f"{family}{v}"
        in n.replace(f"{family}ads", f"{family}").replace(f"{family}ds", f"{family}")
    ]
    if not candidates:
        candidates = [n for n in ALLOWED_AZURE_NODE_TYPES if f"Standard_{family}" in n]
    if candidates:
        # Prefer ds/ads over plain s, higher _vN
        candidates.sort(
            key=lambda n: ("ds" in n or "ads" in n, "_v6" in n, "_v5" in n), reverse=True
        )
        return candidates[0]
    return current_node_type or compose_node_type(family, v)
