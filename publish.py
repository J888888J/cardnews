#!/usr/bin/env python3
"""카드뉴스를 하루 한 편씩 인스타와 스레드에 올린다. GitHub Actions 가 부른다.

이미지는 이 저장소에 있다. 깃허브 주소를 인스타·스레드가 직접 가져가므로
구글 드라이브를 거칠 필요가 없다.

  python publish.py        오늘 차례를 올린다
  python publish.py --dry  올릴 대상만 보여주고 멈춘다

스레드는 THREADS_TOKEN / THREADS_USER_ID 가 있을 때만 올린다(없으면 건너뜀).
인스타와 스레드는 기록을 따로 둔다(done.json / threads_done.json). 한쪽이 실패해도
다른 쪽은 올라가고, 실패한 쪽만 다음 실행에서 다시 시도된다.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

IG_BASE = "https://graph.instagram.com/v21.0"
TH_BASE = "https://graph.threads.net/v1.0"
RAW = os.environ.get("RAW_BASE", "")
TOKEN = os.environ.get("IG_TOKEN", "")
USER = os.environ.get("IG_USER_ID", "")
TH_TOKEN = os.environ.get("THREADS_TOKEN", "")
TH_USER = os.environ.get("THREADS_USER_ID", "")

HERE = os.path.dirname(os.path.abspath(__file__))
DONE = os.path.join(HERE, "done.json")
TH_DONE = os.path.join(HERE, "threads_done.json")
JST = datetime.timezone(datetime.timedelta(hours=9))
START = datetime.date(2026, 10, 13)      # 1일차 = 카페
LAST = 30

IG_CTA = "続けられる場所があります。\nプロフィールのリンクから\n「muwi」をチェックしてみてください☺️"
TH_CTA = "続けられる場所があります👇\nhttps://lp.muwi-life.com/"


class ApiError(Exception):
    pass


def log(m):
    print(f"{datetime.datetime.now(JST):%Y-%m-%d %H:%M}  {m}", flush=True)


def _req(base, token, path, params=None, post=False):
    p = dict(params or {})
    p["access_token"] = token
    url = f"{base}/{path.lstrip('/')}"
    if post:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(p).encode())
    else:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(p))
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ApiError(f"API 에러 {e.code}: {e.read().decode()[:400]}")


def call(path, params=None, post=False):
    return _req(IG_BASE, TOKEN, path, params, post)


def th_call(path, params=None, post=False):
    return _req(TH_BASE, TH_TOKEN, path, params, post)


def load(path):
    return json.load(open(path)) if os.path.exists(path) else []


def mark(path, day):
    d = load(path)
    if day not in d:
        d.append(day)
    json.dump(sorted(d), open(path, "w"))


# ── 인스타 ───────────────────────────────────────────────────────
def wait_ready(cid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = call(cid, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            raise ApiError(f"컨테이너 처리 실패: {cid}")
        time.sleep(5)
    raise ApiError("타임아웃")


def make_carousel(files, caption, video):
    """캐러셀 컨테이너까지만 만든다(발행은 따로). 영상이면 항목마다 VIDEO 컨테이너."""
    children = []
    for n in files:
        url = f"{RAW}/cards/{urllib.parse.quote(n)}"
        if video:
            r = call(f"{USER}/media", {"media_type": "VIDEO", "video_url": url,
                                       "is_carousel_item": "true"}, post=True)
        else:
            r = call(f"{USER}/media", {"image_url": url, "is_carousel_item": "true"},
                     post=True)
        children.append(r["id"])
    for c in children:
        wait_ready(c, timeout=900 if video else 600)
    r = call(f"{USER}/media",
             {"media_type": "CAROUSEL", "children": ",".join(children),
              "caption": caption}, post=True)
    wait_ready(r["id"])
    return r["id"]


def post_instagram(day, names, vids, caption, use_video):
    cid = None
    if use_video:
        try:
            cid = make_carousel(vids, caption, video=True)
        except ApiError as e:
            log(f"[인스타] 영상 캐러셀 준비 실패, 정지 이미지로 올린다: {e}")
    if cid is None:
        cid = make_carousel(names, caption, video=False)
    pub = call(f"{USER}/media_publish", {"creation_id": cid}, post=True)   # 발행은 한 번만
    link = call(pub["id"], {"fields": "permalink"}).get("permalink", "")
    log(f"[인스타] {day}일차 발행 완료 {link}")
    mark(DONE, day)


# ── 스레드 ───────────────────────────────────────────────────────
def threads_text(caption):
    """인스타 캡션을 스레드용으로: CTA 는 링크로(스레드는 링크가 걸린다), 해시태그는 하나만, 500자 이내."""
    t = caption.replace(IG_CTA, TH_CTA)
    lines = t.rstrip().splitlines()
    if lines and lines[-1].lstrip().startswith("#"):
        lines = lines[:-1]
    t = "\n".join(lines).rstrip() + "\n\n#韓国語"
    return t if len(t) <= 500 else t[:497] + "…"


def th_wait(cid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = th_call(cid, {"fields": "status,error_message"})
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise ApiError(f"스레드 컨테이너 실패: {cid} {st.get('error_message', '')}")
        time.sleep(5)
    raise ApiError("스레드 타임아웃")


def th_carousel(files, text, video):
    children = []
    for n in files:
        url = f"{RAW}/cards/{urllib.parse.quote(n)}"
        p = {"is_carousel_item": "true"}
        p.update({"media_type": "VIDEO", "video_url": url} if video
                 else {"media_type": "IMAGE", "image_url": url})
        children.append(th_call(f"{TH_USER}/threads", p, post=True)["id"])
    for c in children:
        th_wait(c)
    r = th_call(f"{TH_USER}/threads", {"media_type": "CAROUSEL",
                                        "children": ",".join(children), "text": text}, post=True)
    th_wait(r["id"])
    return r["id"]


def post_threads(day, names, vids, caption, use_video):
    text = threads_text(caption)
    cid = None
    if use_video:
        try:
            cid = th_carousel(vids, text, video=True)
        except ApiError as e:
            log(f"[스레드] 영상 캐러셀 준비 실패, 정지 이미지로 올린다: {e}")
    if cid is None:
        cid = th_carousel(names, text, video=False)
    pub = th_call(f"{TH_USER}/threads_publish", {"creation_id": cid}, post=True)
    link = th_call(pub["id"], {"fields": "permalink"}).get("permalink", "")
    log(f"[스레드] {day}일차 발행 완료 {link}")
    mark(TH_DONE, day)


# ── 실행 ─────────────────────────────────────────────────────────
def main(dry=False):
    day = (datetime.datetime.now(JST).date() - START).days + 1
    if not 1 <= day <= LAST:
        log(f"올릴 날 아님 ({day}일차)")
        return 0

    names = sorted(n for n in os.listdir(os.path.join(HERE, "cards"))
                   if n.startswith(f"d{day:02d}_insta_") and n.endswith(".png"))
    vids = sorted(n for n in os.listdir(os.path.join(HERE, "cards"))
                  if n.startswith(f"d{day:02d}_insta_") and n.endswith(".mp4"))
    cap_path = os.path.join(HERE, "captions", f"d{day:02d}_인스타.txt")
    if not names or not os.path.exists(cap_path):
        log(f"{day}일차 자료 없음 — 이미지 {len(names)}장")
        return 0
    caption = open(cap_path, encoding="utf-8").read().strip()
    # 영상은 장수가 이미지와 같을 때만 쓴다(일부만 있으면 정지 이미지)
    use_video = len(vids) == len(names) and len(vids) >= 2

    todo = []
    if TOKEN and USER:
        if day in load(DONE):
            log(f"[인스타] {day}일차는 이미 올렸음")
        else:
            todo.append(("인스타", post_instagram))
    if TH_TOKEN and TH_USER:
        if day in load(TH_DONE):
            log(f"[스레드] {day}일차는 이미 올렸음")
        else:
            todo.append(("스레드", post_threads))
    else:
        log("[스레드] THREADS_TOKEN 없음 — 건너뜀")

    log(f"{day}일차 · {len(names)}장 · {'영상' if use_video else '이미지'} · {caption.splitlines()[0]}")
    if dry:
        log("올릴 곳: " + (", ".join(n for n, _ in todo) or "없음"))
        for n in (vids if use_video else names):
            print("  ", f"{RAW}/cards/{urllib.parse.quote(n)}")
        if TH_TOKEN and TH_USER:
            print("--- 스레드 글 ---\n" + threads_text(caption))
        return 0

    failed = 0
    for name, fn in todo:          # 한쪽이 실패해도 다른 쪽은 올린다
        try:
            fn(day, names, vids, caption, use_video)
        except ApiError as e:
            failed += 1
            log(f"[{name}] 실패: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    if not RAW or not ((TOKEN and USER) or (TH_TOKEN and TH_USER)):
        sys.exit("RAW_BASE 와 IG_TOKEN/IG_USER_ID 또는 THREADS_TOKEN/THREADS_USER_ID 가 필요하다")
    sys.exit(main(dry="--dry" in sys.argv))
