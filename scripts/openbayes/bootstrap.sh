#!/usr/bin/env bash
# Create or reuse the restart-safe OpenBayes environment described in docs/openbayes-environment.md.
set -euo pipefail

cdf_workspace="${CDF_WORKSPACE:-/openbayes/home/code-data-factory}"
cdf_python_dir="${UV_PYTHON_INSTALL_DIR:-/openbayes/home/.uv/python}"
cdf_cache_dir="${UV_CACHE_DIR:-/openbayes/home/.cache/uv}"
cdf_output_dir="${CDF_PROBE_OUTPUT_DIR:-$cdf_workspace/artifacts/dependencies}"
cdf_uv_bin="${CDF_UV_BIN:-/openbayes/home/.pylibs/bin/uv}"
cdf_wheelhouse="${CDF_WHEELHOUSE:-/openbayes/home/cdf-wheelhouse}"
cdf_default_index="${CDF_UV_DEFAULT_INDEX:-https://repo.huaweicloud.com/repository/pypi/simple}"
cdf_requirements_file="$cdf_output_dir/locked-requirements.txt"

if [[ "$cdf_workspace" != /openbayes/home/* ]]; then
  echo "CDF_WORKSPACE must be inside /openbayes/home; refusing an ephemeral workspace" >&2
  exit 3
fi
if [[ ! -f "$cdf_workspace/pyproject.toml" || ! -f "$cdf_workspace/uv.lock" ]]; then
  echo "CDF_WORKSPACE must contain this checked-out project and its uv.lock" >&2
  exit 2
fi
if [[ ! -x "$cdf_uv_bin" ]]; then
  cdf_uv_bin="$(command -v uv || true)"
fi
if [[ -z "$cdf_uv_bin" || ! -x "$cdf_uv_bin" ]]; then
  echo "No persistent uv was found. Install pinned uv under /openbayes/home/.pylibs first." >&2
  exit 3
fi

export UV_PYTHON_INSTALL_DIR="$cdf_python_dir"
export UV_CACHE_DIR="$cdf_cache_dir"
mkdir -p "$cdf_python_dir" "$cdf_cache_dir" "$cdf_output_dir"

cd "$cdf_workspace"
"$cdf_uv_bin" venv .venv --python 3.12 --allow-existing
"$cdf_uv_bin" export --frozen --all-groups --no-emit-project --output-file "$cdf_requirements_file" >/dev/null
if [[ -d "$cdf_wheelhouse" ]]; then
  "$cdf_uv_bin" pip install --python .venv/bin/python --require-hashes --no-progress --link-mode=copy \
    --no-index --find-links "$cdf_wheelhouse" -r "$cdf_requirements_file"
else
  "$cdf_uv_bin" pip install --python .venv/bin/python --require-hashes --no-progress --link-mode=copy \
    --default-index "$cdf_default_index" -r "$cdf_requirements_file"
fi
"$cdf_uv_bin" sync --frozen --all-groups --offline --no-build-isolation --no-editable --link-mode=copy
.venv/bin/python scripts/openbayes/verify_linux_dependencies.py --output "$cdf_output_dir/linux_probe.json"
