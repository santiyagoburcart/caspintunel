"""A MySQL dump reader for store imports (v1.56) — text only, nothing in the file is ever executed.

`read_upload(raw, name)` accepts a ``.sql``, ``.sql.gz`` or a ``.zip`` with exactly one ``.sql`` inside (size caps against
zip bombs) and returns the dump as text. `parse(text)` returns ``{table: [ {column: value} ]}`` from the ``CREATE TABLE`` /
``INSERT INTO`` statements (mysqldump and phpMyAdmin styles, with or without a column list). Values: ``None`` for NULL, ``str``
for everything else, quoted strings unescaped, unquoted values stripped.
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile

MAX_UPLOAD = 15 * 1024 * 1024          # the uploaded file (= nginx client_max_body_size; zip it if larger)
MAX_TEXT = 300 * 1024 * 1024           # the dump after unpacking


class DumpError(ValueError):
    def __init__(self, en: str, fa: str):
        super().__init__(en)
        self.en, self.fa = en, fa


def read_upload(raw: bytes, name: str) -> str:
    if len(raw) > MAX_UPLOAD:
        raise DumpError("the file is larger than 15 MB — upload it zipped", "حجم فایل بیشتر از ۱۵ مگابایت است — آن را zip کنید")
    lower = (name or "").lower()
    if raw[:2] == b"PK" or lower.endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise DumpError("not a valid zip file", "فایل zip معتبر نیست") from exc
        sqls = [i for i in z.infolist() if i.filename.lower().endswith(".sql") and not i.is_dir()]
        if len(sqls) != 1:
            raise DumpError("the zip must hold exactly one .sql file", "فایل zip باید دقیقاً یک فایل ‎.sql‎ داشته باشد")
        if sqls[0].file_size > MAX_TEXT:
            raise DumpError("the dump inside the zip is too large", "فایل داخل zip بیش از حد بزرگ است")
        with z.open(sqls[0]) as fh:
            data = fh.read(MAX_TEXT + 1)
    elif raw[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
            data = fh.read(MAX_TEXT + 1)
    else:
        data = raw
    if len(data) > MAX_TEXT:
        raise DumpError("the dump is too large", "فایل پشتیبان بیش از حد بزرگ است")
    text = data.decode("utf-8", errors="replace")
    if "CREATE TABLE" not in text or "INSERT INTO" not in text:
        raise DumpError("this is not a MySQL dump (no CREATE TABLE / INSERT INTO)",
                        "این فایل پشتیبان MySQL نیست (CREATE TABLE / INSERT INTO ندارد)")
    return text


_CREATE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?`([^`]+)` \((.*?)\n\)[^;]*;", re.S)
_COL = re.compile(r"^\s*`([^`]+)`\s+[a-zA-Z]+", re.M)
_INSERT = re.compile(r"INSERT (?:IGNORE )?INTO `([^`]+)`\s*(?:\(([^)]*)\))?\s*VALUES\s*", re.I)
_ESC = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a", "b": "\b"}


def columns(text: str) -> dict[str, list[str]]:
    return {m.group(1): _COL.findall(m.group(2)) for m in _CREATE.finditer(text)}


def _rows(s: str, i: int):
    """The value tuples of one INSERT starting at s[i]; returns (rows, end)."""
    rows, n = [], len(s)
    row, cur, quoted, in_q, depth = [], [], False, False, 0
    while i < n:
        ch = s[i]
        if in_q:
            if ch == "\\" and i + 1 < n:
                cur.append(_ESC.get(s[i + 1], s[i + 1]))
                i += 2
                continue
            if ch == "'":
                if i + 1 < n and s[i + 1] == "'":
                    cur.append("'")
                    i += 2
                    continue
                in_q = False
            else:
                cur.append(ch)
            i += 1
            continue
        if depth == 0:
            if ch == "(":
                depth, row, cur, quoted = 1, [], [], False
            elif ch == ";":
                return rows, i + 1
            i += 1
            continue
        if ch == "'":
            in_q, quoted, cur = True, True, []          # whitespace before the quote is not part of the value
        elif ch == ",":
            row.append(_value(cur, quoted))
            cur, quoted = [], False
        elif ch == ")":
            row.append(_value(cur, quoted))
            rows.append(row)
            depth = 0
        elif not quoted:                     # after a closing quote only whitespace can follow
            cur.append(ch)
        i += 1
    return rows, i


def _value(cur: list, quoted: bool):
    v = "".join(cur)
    if quoted:
        return v
    v = v.strip()
    return None if v.upper() == "NULL" else v


def parse(text: str) -> dict[str, list[dict]]:
    cols = columns(text)
    out: dict[str, list[dict]] = {t: [] for t in cols}
    pos = 0
    while True:                      # sequential: an "INSERT INTO" inside a quoted value is never taken for a statement
        m = _INSERT.search(text, pos)
        if m is None:
            return out
        table = m.group(1)
        names = [c.strip().strip("`") for c in m.group(2).split(",")] if m.group(2) else cols.get(table, [])
        rows, pos = _rows(text, m.end())
        for r in rows:
            out.setdefault(table, []).append(dict(zip(names, r)))
