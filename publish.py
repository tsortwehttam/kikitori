#!/usr/bin/env python3
"""Upload an episode and regenerate the private podcast feed.

    python3 publish.py EPISODE.mp3 --title "..." [--script SCRIPT.json] [--description "..."]

Episodes live in S3 under a secret prefix (FEED_PREFIX in .env); the episode list is
episodes.json next to feed.xml, so the feed can be rebuilt from S3 alone.
The feed URL is https://<cloudfront domain>/<FEED_PREFIX>/feed.xml.
"""
import argparse
import datetime
import email.utils
import html
import json
import os
import subprocess
import tempfile
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
AWS = ["aws", "--profile", "new-account", "--region", "us-east-1"]
STACK = "kikitori"


def env():
    vals = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                vals[k] = v
    return vals


def stack_output(key):
    return subprocess.run(AWS + ["cloudformation", "describe-stacks", "--stack-name", STACK, "--query",
                                 f"Stacks[0].Outputs[?OutputKey=='{key}'].OutputValue", "--output", "text"],
                          check=True, capture_output=True, text=True).stdout.strip()


def s3_put(path, key, bucket, content_type, cache):
    subprocess.run(AWS + ["s3", "cp", path, f"s3://{bucket}/{key}", "--content-type", content_type,
                          "--cache-control", cache, "--only-show-errors"], check=True)


def s3_get_json(key, bucket, default):
    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        r = subprocess.run(AWS + ["s3", "cp", f"s3://{bucket}/{key}", f.name, "--only-show-errors"],
                           capture_output=True)
        if r.returncode:
            return default
        return json.load(open(f.name))


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout
    return int(float(out))


def transcript_html(script):
    rows = []
    for item in script.get("lines", []):
        if "text" in item:
            cls = "en" if item["say"] == "en" else "ja"
            text = html.escape(item["text"])
            rows.append(f"<p><i>{text}</i></p>" if cls == "en" else f"<p>{text}</p>")
    return "\n".join(rows)


def feed_xml(base, episodes):
    items = []
    for e in sorted(episodes, key=lambda e: e["published"], reverse=True):
        notes = html.escape(e.get("description", "")) + (f"<hr>{e['transcript']}" if e.get("transcript") else "")
        items.append(f"""    <item>
      <title>{html.escape(e['title'])}</title>
      <guid isPermaLink="false">{e['guid']}</guid>
      <pubDate>{email.utils.format_datetime(datetime.datetime.fromisoformat(e['published']))}</pubDate>
      <enclosure url="{base}/{e['file']}" length="{e['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{e['seconds']}</itunes:duration>
      <description><![CDATA[{notes}]]></description>
      <content:encoded><![CDATA[{notes}]]></content:encoded>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Kikitori 聞き取り</title>
    <link>{base}/feed.xml</link>
    <language>ja</language>
    <description>Matt's private Japanese listening practice, built from his Anki cards.</description>
    <itunes:author>Kikitori</itunes:author>
    <itunes:image href="{base}/cover.png"/>
    <itunes:block>Yes</itunes:block>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Education"><itunes:category text="Language Learning"/></itunes:category>
{chr(10).join(items)}
  </channel>
</rss>
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mp3")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--script", help="episode script JSON; its lines become the show-notes transcript")
    a = p.parse_args()

    prefix, bucket = env()["FEED_PREFIX"], stack_output("BucketName")
    base = f"https://{stack_output('DistributionDomain')}/{prefix}"
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    file = f"episodes/{now:%Y%m%d-%H%M%S}-{os.path.basename(a.mp3)}"
    script = json.load(open(a.script)) if a.script else {}

    s3_put(a.mp3, f"{prefix}/{file}", bucket, "audio/mpeg", "public, max-age=31536000, immutable")
    cover = os.path.join(ROOT, "cover.png")
    s3_put(cover, f"{prefix}/cover.png", bucket, "image/png", "public, max-age=86400")

    episodes = s3_get_json(f"{prefix}/episodes.json", bucket, [])
    episodes.append({
        "guid": str(uuid.uuid4()), "title": a.title, "description": a.description or script.get("description", ""),
        "file": file, "bytes": os.path.getsize(a.mp3), "seconds": duration(a.mp3),
        "published": now.isoformat(), "transcript": transcript_html(script),
    })
    with tempfile.TemporaryDirectory() as tmp:
        ep, feed = os.path.join(tmp, "episodes.json"), os.path.join(tmp, "feed.xml")
        json.dump(episodes, open(ep, "w"), ensure_ascii=False, indent=1)
        open(feed, "w").write(feed_xml(base, episodes))
        s3_put(ep, f"{prefix}/episodes.json", bucket, "application/json", "no-cache")
        s3_put(feed, f"{prefix}/feed.xml", bucket, "application/rss+xml; charset=utf-8", "public, max-age=300")
    print(f"Published {a.title}\nFeed: {base}/feed.xml")


if __name__ == "__main__":
    main()
