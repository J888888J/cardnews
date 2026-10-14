#!/usr/bin/env python3
"""카드뉴스를 하루 한 장씩 인스타에 올린다. GitHub Actions 가 부른다.

이미지는 이 저장소에 있다. 깃허브 주소를 인스타가 직접 가져가므로
구글 드라이브를 거칠 필요가 없다.

  python publish.py        오늘 차례를 올린다
  python publish.py --dry  올릴 대상만 보여주고 멈춘다
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://graph.instagram.com/v21.0"
RAW = os.environ.get("RAW_BASE", "")
TOKEN = os.environ.get("IG_TOKEN", "")
USER = os.environ.get("IG_USER_ID", "")

HERE = os.path.dirname(os.path.abspath(__file__))
DONE = os.path.join(HERE, "done.json")
JST = datetime.timezone(datetime.timedelta(hours=9))
START = datetime.date(2026, 10, 13)      # 1일차 = 카페
LAST = 30


def log(m):
    print(f"{datetime.datetime.now(JST):%Y-%m-%d %H:%M}  {m}", flush=True)


def call(path, params=None, post=False):
    p = dict(params or {})
    p["access_token"] = TOKEN
    url = f"{BASE}/{path.lstrip('/')}"
    if post:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(p).encode())
    else:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(p))
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API 에러 {e.code}: {e.read().decode()[:400]}")


def wait_ready(cid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = call(cid, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            sys.exit(f"컨테이너 처리 실패: {cid}")
        time.sleep(5)
    sys.exit("타임아웃")


def main(dry=False):
    day = (datetime.datetime.now(JST).date() - START).days + 1
    if not 1 <= day <= LAST:
        log(f"올릴 날 아님 ({day}일차)")
        return
    done = json.load(open(DONE)) if os.path.exists(DONE) else []
    if day in done:
        log(f"{day}일차는 이미 올렸음")
        return

    names = sorted(n for n in os.listdir(os.path.join(HERE, "cards"))
                   if n.startswith(f"d{day:02d}_insta_") and n.endswith(".png"))
    cap_path = os.path.join(HERE, "captions", f"d{day:02d}_인스타.txt")
    if not names or not os.path.exists(cap_path):
        log(f"{day}일차 자료 없음 — 이미지 {len(names)}장")
        return
    caption = open(cap_path, encoding="utf-8").read().strip()

    log(f"{day}일차 · {len(names)}장 · {caption.splitlines()[0]}")
    if dry:
        for n in names:
            print("  ", f"{RAW}/cards/{urllib.parse.quote(n)}")
        return

    children = []
    for n in names:
        url = f"{RAW}/cards/{urllib.parse.quote(n)}"
        r = call(f"{USER}/media", {"image_url": url, "is_carousel_item": "true"},
                 post=True)
        children.append(r["id"])
    for c in children:
        wait_ready(c)

    r = call(f"{USER}/media",
             {"media_type": "CAROUSEL", "children": ",".join(children),
              "caption": caption}, post=True)
    wait_ready(r["id"])
    pub = call(f"{USER}/media_publish", {"creation_id": r["id"]}, post=True)
    link = call(pub["id"], {"fields": "permalink"}).get("permalink", "")
    log(f"{day}일차 발행 완료 {link}")

    done.append(day)
    json.dump(sorted(done), open(DONE, "w"))


if __name__ == "__main__":
    if not TOKEN or not USER or not RAW:
        sys.exit("IG_TOKEN / IG_USER_ID / RAW_BASE 가 없다")
    main(dry="--dry" in sys.argv)
