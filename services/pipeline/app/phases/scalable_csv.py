from __future__ import annotations

import os
import tempfile
from pathlib import Path

import dask.dataframe as dd
import pandas as pd

from app.dask_runtime import get_dask_client


def read_csv_with_dask(content: bytes, source_name: str) -> pd.DataFrame:
    """
    Lee un CSV usando Dask DataFrame y devuelve un pandas.DataFrame.

    Importante:
    en modo distribuido, el worker de Dask ejecuta la lectura. Por eso el CSV
    temporal debe guardarse en una ruta compartida entre `pipeline` y
    `dask-worker`, no en /tmp local del contenedor pipeline.
    """
    suffix = Path(source_name).suffix or ".csv"
    blocksize = os.getenv("DASK_CSV_BLOCKSIZE", "16MB")

    shared_tmp_dir = Path(os.getenv("DASK_SHARED_TMP_DIR", "/app/data/tmp/dask"))
    shared_tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
            dir=str(shared_tmp_dir),
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        with get_dask_client() as client:
            ddf = dd.read_csv(
                tmp_path,
                blocksize=blocksize,
            )

            partitions = ddf.npartitions
            df = ddf.compute()

            df.attrs["processing_engine"] = "dask"
            df.attrs["dask_partitions"] = partitions
            df.attrs["dask_blocksize"] = blocksize

            try:
                df.attrs["dask_scheduler"] = client.scheduler_info().get(
                    "address",
                    "unknown",
                )
            except Exception:
                df.attrs["dask_scheduler"] = "unknown"

            return df

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)