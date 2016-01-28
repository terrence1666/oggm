"""Wrappers for the single tasks, multi processor handling."""
from __future__ import division

# Built ins
import logging
import os
# External libs
import pandas as pd
import multiprocessing as mp

# Locals
import oggm
from oggm import cfg, tasks, utils


# Module logger
log = logging.getLogger(__name__)

# Multiprocessing pool
mppool = None


def _init_pool():
    """Necessary because at import time, cfg might be unitialized"""

    global mppool
    if cfg.PARAMS['use_multiprocessing']:
        mppool = mp.Pool(cfg.PARAMS['mp_processes'])


def execute_entity_task(task, gdirs):
    """Execute a task on gdirs.

    If you asked for multiprocessing, it will do it.

    Parameters
    ----------
    task: function
        the entity task to apply
    gdirs: list
        the list of oggm.GlacierDirectory to process
    """

    if cfg.PARAMS['use_multiprocessing']:
        if mppool is None:
            _init_pool()
        poolargs = gdirs
        mppool.map(task, poolargs, chunksize=1)
    else:
        for gdir in gdirs:
            task(gdir)


def init_glacier_regions(rgidf, reset=False, force=False):
    """Very first task to do (always).

    Set reset=True in order to delete the content of the directories.
    """

    if reset and not force:
        reset = utils.query_yes_no('Delete all glacier directories?')

    gdirs = []
    for _, entity in rgidf.iterrows():
        gdir = oggm.GlacierDirectory(entity, reset=reset)
        if not os.path.exists(gdir.get_filepath('dem')):
            tasks.define_glacier_region(gdir, entity=entity)
        gdirs.append(gdir)

    return gdirs


def gis_prepro_tasks(gdirs):
    """Prepare the flowlines."""

    task_list = [
        tasks.glacier_masks,
        tasks.compute_centerlines,
        tasks.compute_downstream_lines,
        tasks.catchment_area,
        tasks.initialize_flowlines,
        tasks.catchment_width_geom,
        tasks.catchment_width_correction
    ]
    for task in task_list:
        execute_entity_task(task, gdirs)


def climate_tasks(gdirs):
    """Prepare the climate data."""

    # Global task
    tasks.distribute_climate_data(gdirs)

    # Get ref glaciers (all glaciers with MB)
    dfids = cfg.PATHS['wgms_rgi_links']
    dfids = pd.read_csv(dfids)['RGI_ID'].values
    ref_gdirs = [g for g in gdirs if g.rgi_id in dfids]
    execute_entity_task(tasks.mu_candidates, ref_gdirs)

    # Global tasks
    tasks.compute_ref_t_stars(ref_gdirs)
    tasks.distribute_t_stars(gdirs)


def inversion_tasks(gdirs):
    """Invert the bed topography."""

    # Init
    execute_entity_task(tasks.prepare_for_inversion, gdirs)

    # Global task
    tasks.optimize_inversion_params(gdirs)

    # Inversion for all glaciers
    execute_entity_task(tasks.volume_inversion, gdirs)
