import pytest

from apps.accounts.models import User
from apps.settings_app.utils import set_setting
from apps.telegram.gate import check_access, missing_channel_memberships
from apps.telegram.models import RequiredChannel

pytestmark = pytest.mark.django_db


class FakeClient:
    def __init__(self, member=True):
        self.member = member

    def is_member(self, chat_id, user_id):
        return self.member


@pytest.fixture
def user():
    return User.objects.create_user("u", "Str0ngPass!", telegram_id=1)


def test_no_forced_join_means_open(user):
    set_setting("force_channel_join", "false", "bool")
    RequiredChannel.objects.create(channel_id="@c", is_active=True)
    assert missing_channel_memberships(1, client=FakeClient(member=False)) == []
    assert check_access(user, 1, client=FakeClient(member=False)).ok is True


def test_missing_channel_blocks(user):
    set_setting("force_channel_join", "true", "bool")
    RequiredChannel.objects.create(channel_id="@c1", title="C1", is_active=True)
    result = check_access(user, 1, client=FakeClient(member=False))
    assert result.ok is False
    assert [c.channel_id for c in result.missing_channels] == ["@c1"]


def test_member_of_all_channels_passes(user):
    set_setting("force_channel_join", "true", "bool")
    RequiredChannel.objects.create(channel_id="@c1", is_active=True)
    assert check_access(user, 1, client=FakeClient(member=True)).ok is True


def test_phone_requirement(user):
    set_setting("force_channel_join", "false", "bool")
    set_setting("force_share_phone", "true", "bool")
    assert check_access(user, 1, client=FakeClient()).need_phone is True
    user.phone = "0912"
    user.save()
    assert check_access(user, 1, client=FakeClient()).ok is True
