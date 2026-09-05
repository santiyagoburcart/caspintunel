"""Server resource sampling (data-model · `resource_stat`)."""
from __future__ import annotations

import logging

import psutil
from django.conf import settings

from .models import ResourceStat

log = logging.getLogger("caspintunel")


def sample_resources() -> ResourceStat:
    net = psutil.net_io_counters()
    net_in, net_out = net.bytes_recv, net.bytes_sent

    prev = ResourceStat.objects.order_by("-sampled_at").first()
    if prev and net_in >= prev.net_in and net_out >= prev.net_out:
        bandwidth_used = (net_in - prev.net_in) + (net_out - prev.net_out)
    else:
        bandwidth_used = 0  # first sample or counters reset (reboot)

    try:
        disk = psutil.disk_usage(settings.RESOURCE_DISK_PATH).percent
    except OSError:
        disk = 0.0

    return ResourceStat.objects.create(
        cpu_percent=psutil.cpu_percent(interval=0.5),
        ram_percent=psutil.virtual_memory().percent,
        swap_percent=psutil.swap_memory().percent,
        disk_percent=disk,
        net_in=net_in,
        net_out=net_out,
        bandwidth_used=bandwidth_used,
    )
