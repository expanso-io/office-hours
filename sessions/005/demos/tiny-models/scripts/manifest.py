"""Write .models/manifest.json: what each model is and how big it is on disk.

Run by `just warm` while llama-server is up, so the direct model's parameter
count comes from the server that will serve it. The cockpit reads this file.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


def get(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main(
    models_dir: Path,
    ollama_url: str,
    ollama_model: str,
    direct_url: str,
    direct_name: str,
    gguf: str,
):
    scorer = json.loads((models_dir / "scorer.json").read_text())
    manifest = {
        "python": {
            "name": "IsolationForest",
            "wiring": "subprocess",
            "bytes": scorer["bytes"],
            "shape": f"{scorer['trees']} trees, {scorer['nodes']:,} nodes, scikit-learn",
        }
    }

    ollama = {"name": ollama_model, "wiring": "ollama_chat"}
    for model in get(f"{ollama_url}/api/tags").get("models", []):
        if ollama_model in (model.get("name"), model.get("model")):
            details = model.get("details", {})
            ollama["bytes"] = model.get("size")
            ollama["shape"] = (
                f"{details.get('parameter_size')} parameters, {details.get('quantization_level')}"
            )
    manifest["ollama"] = ollama

    direct = {"name": direct_name, "wiring": "http"}
    base = direct_url.removesuffix("/chat/completions")
    for model in get(f"{base}/models").get("data", []):
        meta = model.get("meta") or {}
        if model.get("id") == direct_name and meta:
            direct["shape"] = (
                f"{meta['n_params'] / 1e6:.1f}M parameters, {meta.get('ftype', 'GGUF')}"
            )
    if Path(gguf).is_file() and direct_url.startswith("http://127.0.0.1"):
        direct["bytes"] = Path(gguf).stat().st_size
    manifest["direct"] = direct

    (models_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for key, info in manifest.items():
        print(
            f"{key:7} {info['name']:16} {info.get('bytes', 0):>12,} bytes  {info.get('shape', '')}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), *sys.argv[2:7])
