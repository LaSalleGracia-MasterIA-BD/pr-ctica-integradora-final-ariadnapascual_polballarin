from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from dask.distributed import Client, LocalCluster

logger = logging.getLogger(__name__)


@contextmanager
def get_dask_client() -> Iterator[Client]:
    """
    Devuelve un cliente Dask.

    Prioridad:
    1. Cluster distribuido definido por DASK_SCHEDULER_ADDRESS.
    2. Fallback a LocalCluster si el scheduler no está disponible.

    Esto permite que el pipeline funcione tanto dentro de Docker Compose
    como en ejecución local de desarrollo.
    """
    scheduler_address = os.getenv("DASK_SCHEDULER_ADDRESS", "").strip()
    cluster = None
    client = None

    try:
        if scheduler_address:
            try:
                client = Client(
                    scheduler_address,
                    timeout=os.getenv("DASK_CONNECT_TIMEOUT", "5s"),
                    set_as_default=True,
                )
                logger.info(
                    "dask.connected",
                    extra={"scheduler_address": scheduler_address},
                )
            except Exception as exc:
                logger.warning(
                    "dask.scheduler_unavailable_fallback_local",
                    extra={
                        "scheduler_address": scheduler_address,
                        "error": str(exc),
                    },
                )

        if client is None:
            cluster = LocalCluster(
                n_workers=int(os.getenv("DASK_LOCAL_WORKERS", "2")),
                threads_per_worker=int(os.getenv("DASK_LOCAL_THREADS_PER_WORKER", "1")),
                memory_limit=os.getenv("DASK_LOCAL_MEMORY_LIMIT", "1GB"),
                dashboard_address=None,
                processes=True,
            )
            client = Client(cluster, set_as_default=True)
            logger.info("dask.local_cluster_started")

        yield client

    finally:
        if client is not None:
            client.close()
        if cluster is not None:
            cluster.close()