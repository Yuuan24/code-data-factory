# OpenBayes restart-safe dependency environment

The normative agent procedure, failure-closure rules, and acceptance conditions are in
[the rented Linux recovery contract](../specs/001-code-data-factory/contracts/rented-environment-recovery.md).
This guide supplies the repository-specific OpenBayes paths and observed provider facts.

This repository requires Python 3.12. OpenBayes documents that traditional containers clear the system disk,
including `/tmp`, `/opt/venv`, manually installed system packages, and default Python packages, when a
container closes or is continued. The documented persistent workspace is `/openbayes/home`; within one reused
workspace/storage context, the project checkout, Python interpreter download, virtual environment, cache, and
probe evidence therefore all belong below that directory.

The checked host confirmed that `/openbayes/home` is present and mounted as `/output`, but its current image
has Python 3.10 and no `uv`. Do not run this project from `/root` or `/tmp`, and do not install it into
`/opt/venv`: those locations do not meet the restart requirement.

## One-time runtime choice

Prefer an OpenBayes **uv runtime** before running the project. The official guide states that newer Ubuntu
uv runtimes include `uv`. When the selected image lacks it, the pinned `uv==0.11.7` bootstrap package may be
installed with `pip install --user` after setting `PYTHONUSERBASE=/openbayes/home/.pylibs`; this is the guide's
documented persistent user-package location and does not change system Python or `/opt/venv`. The project then
uses `/openbayes/home/.pylibs/bin/uv`, rejecting an unpinned or transient installer. Place a checkout containing
`pyproject.toml` and `uv.lock` at:

```bash
/openbayes/home/code-data-factory
```

## Bootstrap and every later restart

From the persistent checkout, run:

```bash
scripts/openbayes/bootstrap.sh
```

The script sets `UV_PYTHON_INSTALL_DIR=/openbayes/home/.uv/python` before obtaining Python 3.12 and creates
`/openbayes/home/code-data-factory/.venv`. It exports the exact frozen lock to a hash-pinned requirements file,
installs that file with `uv pip install --require-hashes`, then uses offline `uv sync` only to build the trusted
local project as a non-editable wheel. This avoids a lock-file artifact URL bypassing the selected mirror, and
does not relax versions or hashes for third-party packages. Its default index is the Huawei Cloud mirror, selected
from a 2026-09-08 same-host comparison of a 45.4 MiB locked Linux wheel: Huawei completed in 4 seconds, Tsinghua
completed in 5 seconds, and PyPI timed out after 180 seconds. Override the selected mirror only with
`CDF_UV_DEFAULT_INDEX`; the lock remains authoritative for versions and hashes. The script then writes the Linux
installation/read-write result to `artifacts/dependencies/linux_probe.json`.

### Persistence boundary verified on 2026-09-08

Do **not** interpret `/openbayes/home` as a guarantee that data survives a new rented instance or a newly
created workspace. On the replacement rental instance, `/openbayes/home` was again a Ceph-backed mount, but the
previous checkout, persistent `uv`, downloaded Python, cache, and `.venv` were all absent. This is consistent
with persistence being scoped to the storage/workspace identity rather than to the OpenBayes account or host name.
The platform documentation supports persistence for the same mounted workspace; it does not prove cross-instance
reuse of a different rental workspace.

Therefore Git (or another versioned source transfer) is the recovery source of truth. For every new rental
instance, transfer or clone the checked-out source and its `uv.lock` into `/openbayes/home/code-data-factory`,
then rerun `scripts/openbayes/bootstrap.sh`. A reused workspace can benefit from the `/openbayes/home` Python,
cache, and virtual environment, but those are only accelerators—not the only copy of source code, lock file, or
evidence artifacts. Export the resulting evidence outside the rental workspace when it must survive an
independent instance replacement.

## Optional offline wheelhouse

For a slow or metered remote network, prepare an **x86_64 Linux / CPython 3.12** wheelhouse from the frozen
`uv.lock` on a faster trusted machine, then copy it to `/openbayes/home/cdf-wheelhouse`. Do not place macOS
wheels or a copied macOS virtual environment there. When that directory exists, `bootstrap.sh` automatically
exports the frozen hash-pinned requirements and uses `uv pip install --require-hashes --no-index --find-links`
against that wheelhouse; it still uses the checked-in lock and fails if a locked distribution is absent. Set
`CDF_WHEELHOUSE` only to choose a different persistent wheelhouse path. The transferred artifacts save remote
download time, but consume persistent storage and must be regenerated whenever `uv.lock` changes.

The probe succeeds only when every declared component is installed on Linux and Pydantic plus PyArrow complete
a Parquet write/read round trip. It does not run a model, launch Ray, or claim isolated execution/training
evidence.

## Source and limits

This procedure follows OpenBayes's [storage persistence guide](https://openbayes.com/docs/gear/storage-persistence/)
(updated 2026-06-10) and [uv environment guide](https://openbayes.com/docs/gear/uv/) (updated 2026-07-23).
The platform says that `pip install --user` can persist a small number of packages, but its uv guide recommends
a virtual environment under `/openbayes/home` for an isolated project and a different Python version. That is
the applicable pattern here; the project must not rely on transient `--user` packages.
