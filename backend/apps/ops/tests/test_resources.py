import pytest

from apps.ops.models import ResourceStat
from apps.ops.resources import sample_resources

pytestmark = pytest.mark.django_db


def test_sample_creates_row_with_sane_values():
    stat = sample_resources()
    assert 0 <= stat.cpu_percent <= 100
    assert 0 <= stat.ram_percent <= 100
    assert stat.net_in >= 0 and stat.net_out >= 0
    assert stat.bandwidth_used == 0  # first sample


def test_bandwidth_used_is_delta_from_previous():
    ResourceStat.objects.create(cpu_percent=1, ram_percent=1, disk_percent=1,
                                net_in=1000, net_out=2000, bandwidth_used=0)
    stat = sample_resources()
    # current counters are >= the tiny seeded values, so we get a positive delta
    assert stat.bandwidth_used == (stat.net_in - 1000) + (stat.net_out - 2000)
    assert stat.bandwidth_used >= 0
