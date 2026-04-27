from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_project_env(*, override: bool = False) -> Path:
    env_path = project_root() / ".env"
    if not env_path.is_file():
        return env_path

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value

    return env_path


def set_project_env(entries: dict[str, str]) -> Path:
    env_path = project_root() / ".env"
    existing_lines = []
    if env_path.is_file():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    kv_map: dict[str, str] = {}
    for raw_line in existing_lines:
        s = raw_line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        kv_map[k.strip()] = v.strip()
    for k, v in entries.items():
        kv_map[k] = v
    out_lines: list[str] = []
    seen: set[str] = set()
    for raw_line in existing_lines:
        s = raw_line.strip()
        if not s or s.startswith("#") or "=" not in s:
            out_lines.append(raw_line)
            continue
        k, _ = s.split("=", 1)
        kk = k.strip()
        if kk in kv_map:
            out_lines.append(f"{kk}={kv_map[kk]}")
            seen.add(kk)
        else:
            out_lines.append(raw_line)
    for k, v in kv_map.items():
        if k not in seen:
            out_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return env_path


def read_project_env() -> dict[str, str]:
    env_path = project_root() / ".env"
    kv_map: dict[str, str] = {}
    if not env_path.is_file():
        return kv_map
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        s = raw_line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        kv_map[k.strip()] = v.strip()
    return kv_map


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "*" * len(v)
    return "*" * (len(v) - 6) + v[-6:]


def get_project_env_values(keys: list[str], *, mask_secrets: bool = True) -> dict[str, dict[str, str | bool]]:
    kv = read_project_env()
    secret_keys = {"OPENAI_API_KEY", "MINIMAX_API_KEY"}
    result: dict[str, dict[str, str | bool]] = {}
    for k in keys:
        raw = kv.get(k, "")
        has_value = bool(raw)
        if mask_secrets and k in secret_keys and has_value:
            masked = _mask_secret(raw)
        else:
            masked = raw
        result[k] = {"has_value": has_value, "value": masked}
    return result
