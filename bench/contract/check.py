#!/usr/bin/env python3
"""check.py --port N [--skip name,...] [--only name,...] [-v]

The byte comparison every server passes before any load (bench/contract/
README.md): each probe in probes.tsv is sent to 127.0.0.1:N and the status,
the Content-Type prefix and the body bytes are compared with the golden file.

JSON bodies compare byte for byte. HTML bodies compare byte for byte after one
canonicalization: equivalent character references are written one way, the way
the golden (Jinja2, MarkupSafe) writes them. `&quot;` `&#x22;` `&#34;` become
`&#34;`, `&#x27;` `&apos;` `&#39;` become `&#39;`, and a numeric reference to a
non-ASCII code point becomes the UTF-8 character. `&lt;`, `&gt;` and `&amp;`
are left alone, so a page that fails to escape `<script>` still differs.

Exit 0 when every selected probe matches; 1 with a diff otherwise; 2 when the
server cannot be reached.
"""
import argparse
import http.client
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = "bench-7f3c9a1e"


def probes():
    out = []
    for line in open(os.path.join(HERE, "probes.tsv"), encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        name, method, path, auth, req, status, expected, ctype = line.rstrip("\n").split("\t")
        out.append(dict(name=name, method=method, path=path, auth=auth, req=req,
                        status=int(status), expected=expected, ctype=ctype))
    return out


def canonical_html(b):
    s = b.decode("utf-8")
    s = re.sub(r"&quot;|&#x0*22;|&#0*34;", "&#34;", s, flags=re.I)
    s = re.sub(r"&apos;|&#x0*27;|&#0*39;", "&#39;", s, flags=re.I)

    def num(m):
        cp = int(m.group(1)[1:], 16) if m.group(1)[0] in "xX" else int(m.group(1))
        return chr(cp) if cp > 127 else m.group(0)

    s = re.sub(r"&#([xX][0-9a-fA-F]+|[0-9]+);", num, s)
    return s.encode("utf-8")


def send(host, port, p):
    headers = {"Accept": "*/*"}
    body = None
    if p["req"] != "-":
        body = open(os.path.join(HERE, p["req"]), "rb").read()
        headers["Content-Type"] = "application/json"
    if p["auth"] == "token":
        headers["Authorization"] = f"Bearer {TOKEN}"
    elif p["auth"] == "wrong":
        headers["Authorization"] = "Bearer not-the-token"
    c = http.client.HTTPConnection(host, port, timeout=30)
    c.request(p["method"], p["path"], body=body, headers=headers)
    r = c.getresponse()
    data = r.read()
    ctype = r.getheader("Content-Type", "")
    c.close()
    return r.status, ctype, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--skip", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(",")))
    only = set(filter(None, a.only.split(",")))
    bad = 0
    n = 0
    for p in probes():
        if p["name"] in skip or (only and p["name"] not in only):
            continue
        n += 1
        try:
            status, ctype, data = send(a.host, a.port, p)
        except OSError as e:
            print(f"{p['name']}: cannot reach {a.host}:{a.port}: {e}")
            return 2
        want = open(os.path.join(HERE, p["expected"]), "rb").read()
        got = data
        if p["ctype"] == "text/html":
            want, got = canonical_html(want), canonical_html(data)
        problems = []
        if status != p["status"]:
            problems.append(f"status {status}, expected {p['status']}")
        if not ctype.lower().startswith(p["ctype"]):
            problems.append(f"Content-Type '{ctype}', expected {p['ctype']}")
        if got != want:
            problems.append(f"body differs:\n    got:      {data[:400]!r}\n    expected: {want[:400]!r}")
        if problems:
            bad += 1
            print(f"{p['name']}: " + "; ".join(problems))
        elif a.v:
            print(f"{p['name']}: equal ({len(data)} bytes)")
    if n == 0:
        print("no probe selected")
        return 1
    print(f"check: {n - bad}/{n} probes equal")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
