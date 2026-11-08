"""v1.46 (multi-tenant Phase 4): a Celery task runs for the store it was queued from.

`before_task_publish` stamps the tenant set by the sender (a web request on a store's domain, a task already running for a
store, an explicit `tenant_context`) into the message headers; `task_prerun` restores it in the worker before the task
body runs and `task_postrun` clears it. Messages without the header (beat, our own default-tenant code, messages queued
before this release) keep running in the default tenant exactly as before. Periodic jobs that work on customer data loop
over every store themselves (`context.for_each_tenant`).
"""
from __future__ import annotations

from celery.signals import before_task_publish, task_postrun, task_prerun

from . import context

HEADER = "caspin_tenant"
_tokens: dict[str, object] = {}


@before_task_publish.connect(weak=False)
def stamp_tenant(headers=None, **_kw):
    if headers is None or HEADER in headers or context.is_unscoped():
        return
    tid = context._current.get()                 # only an explicitly set tenant — never guess
    if tid is not None:
        headers[HEADER] = int(tid)


def _header(task):
    req = getattr(task, "request", None)
    if req is None:
        return None
    tid = getattr(req, HEADER, None)
    if tid is None:
        tid = (getattr(req, "headers", None) or {}).get(HEADER)
    return tid


@task_prerun.connect(weak=False)
def restore_tenant(task_id=None, task=None, **_kw):
    tid = _header(task)
    if tid not in (None, ""):
        _tokens[task_id] = context.set_tenant(int(tid))


@task_postrun.connect(weak=False)
def clear_tenant(task_id=None, **_kw):
    tok = _tokens.pop(task_id, None)
    if tok is not None:
        context.reset_tenant(tok)
