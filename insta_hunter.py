#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""insta_hunter.py — صيّاد يوزرات إنستغرام (1-4 أحرف). ملف واحد، stdlib فقط."""

import argparse, gzip, itertools, os, random, re, string, sys, threading, time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

APP_ID = "3419628305025917"  # أندرويد ويب فيو: يعمل بدون تسجيل دخول
UA_ANDROID = ("Mozilla/5.0 (Linux; Android 14; SM-S921B Build/UP1A.231005.007; wv) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.0.0 "
              "Mobile Safari/537.36 Instagram 340.0.0.36.90 Android (34/14; 480dpi; "
              "1080x2340; samsung; SM-S921B; e1s; s5e9945; en_US; 629151101)")
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
API = "https://i.instagram.com/api/v1/users/web_profile_info/?username={}"
PROFILE = "https://www.instagram.com/{}/"
CHARS = re.compile(r"^[a-z0-9._]+$")


def valid(u, hi):
    if not u or len(u) > hi or not CHARS.match(u):
        return False
    if u[0] in "._" or u[-1] in "._":
        return False
    return not any(b in u for b in ("__", "..", "._", "_."))


def http_get(url, headers, timeout=15):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code, enc = r.read(), r.status, r.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as e:
        raw, code, enc = e.read(), e.code, (e.headers.get("Content-Encoding", "") if e.headers else "")
    except Exception:
        return 0, ""
    if enc == "gzip":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return code, raw.decode("utf-8", "replace")


def headers(ua, app_id, sid, html=False):
    h = {"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9",
         "Accept-Encoding": "gzip, deflate"}
    if app_id:
        h["X-IG-App-ID"] = app_id
        h["Accept"] = "*/*"
        h["Referer"] = "https://www.instagram.com/"
    else:
        h["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    if sid:
        h["Cookie"] = "sessionid=" + sid
    return h


def api_check(u, sid, t):
    app_id = "936619743392459" if sid else APP_ID
    code, body = http_get(API.format(u), headers(UA_ANDROID, app_id, sid), t)
    if code == 200:
        if re.search(r'"user"\s*:\s*\{', body):
            return "TAKEN"
        if re.search(r'"user"\s*:\s*null', body):
            return "FREE"
        return "ERROR"
    if code == 404:
        return "FREE"
    return "ERROR"


def html_check(u, sid, t):
    code, body = http_get(PROFILE.format(u), headers(UA_DESKTOP, None, sid), t)
    if code == 404:
        return "FREE"
    if code != 200:
        return "UNKNOWN"
    low = body.lower()
    if "isn't available" in low or "isn&#39;t available" in low or "page not found" in low:
        return "FREE"
    m = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', body, re.I)
    if m:
        return "TAKEN" if m.group(1).lower().rstrip("/").endswith("/" + u) else "FREE"
    return "TAKEN" if 'property="og:description"' in low else "FREE"


def check(u, sid, t, confirm):
    r = api_check(u, sid, t)
    if r == "TAKEN" or (r == "FREE" and not confirm):
        return r
    h = html_check(u, sid, t)
    return h if h in ("TAKEN", "FREE") else (r if r == "FREE" else "UNKNOWN")


def gen(mode, lo, hi, alpha):
    if mode == "brute":
        def src():
            for n in range(lo, hi + 1):
                for t in itertools.product(alpha, repeat=n):
                    yield "".join(t)
    else:
        def src():
            while True:
                n = random.randint(lo, hi)
                yield "".join(random.choice(alpha) for _ in range(n))
    seen = set()
    for u in src():
        if u not in seen:
            seen.add(u)
            if valid(u, hi):
                yield u


def main():
    env = os.environ.get
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["random", "brute"], default="random")
    p.add_argument("--min", type=int, default=int(env("MIN", 4)))
    p.add_argument("--max", type=int, default=int(env("MAX", 4)))
    p.add_argument("--limit", type=int, default=int(env("LIMIT", 100000)))
    p.add_argument("--threads", type=int, default=int(env("THREADS", 3)))
    p.add_argument("--delay", type=float, default=float(env("DELAY", 0.3)))
    p.add_argument("--alphabet", default=env("ALPHABET", string.ascii_lowercase + string.digits + "_"))
    p.add_argument("--sessionid", default=env("IG_SESSIONID", ""))
    p.add_argument("--out", default=env("OUT", "insta_hits.txt"))
    p.add_argument("--no-confirm", action="store_true")
    p.add_argument("--no-calibrate", action="store_true")
    a = p.parse_args()

    if not a.no_calibrate:
        print("[*] فحص تجريبي ...", flush=True)
        print("    instagram -> " + check("instagram", a.sessionid, 15, True))
        print("    شبحي عشوائي -> " + check("zz" + "q" * 20, a.sessionid, 15, True), flush=True)

    lock, st = threading.Lock(), {"n": 0, "free": 0, "taken": 0, "err": 0}
    out = open(a.out, "a", encoding="utf-8")

    def done(u, res):
        with lock:
            st["n"] += 1
            if res == "FREE":
                st["free"] += 1
                out.write(u + "\n")
                out.flush()
                print("[+] FREE   " + u, flush=True)
            elif res == "TAKEN":
                st["taken"] += 1
            else:
                st["err"] += 1

    it, pending, sub = gen(a.mode, a.min, a.max, "".join(dict.fromkeys(a.alphabet.lower()))), {}, 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
            while True:
                while len(pending) < a.threads * 4 and sub < a.limit:
                    try:
                        u = next(it)
                    except StopIteration:
                        break
                    pending[ex.submit(check, u, a.sessionid, 15, not a.no_confirm)] = u
                    sub += 1
                if not pending:
                    break
                fin, _ = wait(list(pending), return_when=FIRST_COMPLETED)
                for f in fin:
                    u = pending.pop(f)
                    try:
                        done(u, f.result())
                    except Exception:
                        done(u, "UNKNOWN")
    except KeyboardInterrupt:
        print("\n[!] وقفت يدويًا", flush=True)

    out.close()
    print("تم: فحص=%d متاح=%d محجوز=%d خطأ=%d" %
          (st["n"], st["free"], st["taken"], st["err"]), flush=True)


if __name__ == "__main__":
    main()
