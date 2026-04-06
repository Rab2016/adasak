#!/usr/bin/env python3
"""
Generate an RSS feed from a persianblog.ir HTML backup.
Usage: python generate_rss.py <path_to_post_folder> <your_github_pages_url>

Example:
  python generate_rss.py ./post https://rab2016.github.io/adasak
"""

import os
import sys
import re
from datetime import datetime
from html.parser import HTMLParser
import html

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Persian/Jalali month lengths (non-leap year)
JALALI_DAYS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

def jalali_to_gregorian(jy, jm, jd):
    """Convert a Jalali (Solar Hijri) date to Gregorian."""
    jy -= 979
    jm -= 1
    jd -= 1
    j_day_no = 365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4
    for i in range(jm):
        j_day_no += JALALI_DAYS[i]
    j_day_no += jd
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        leap = False if g_day_no % 365 == 0 else True  # noqa
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    g_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for i, days in enumerate(g_days):
        if g_day_no < days:
            gm = i + 1
            break
        g_day_no -= days
    gd = g_day_no + 1
    return gy, gm, gd


def parse_persian_digits(s):
    """Convert Persian/Arabic-Indic digits to ASCII digits."""
    mapping = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    return s.translate(mapping)


class PostParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_posttitle_a = False
        self.in_writer = False
        self.in_postcontent = False
        self.title = ''
        self.date_raw = ''
        self.content_html = ''
        self._depth = 0
        self._content_depth = None
        self._current_tag_class = ''

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get('class', '')

        if 'posttitle' in cls and tag == 'a':
            self.in_posttitle_a = True

        if cls == 'writer':
            self.in_writer = True

        if cls == 'postcontent':
            self.in_postcontent = True
            self._content_depth = 0

        if self.in_postcontent:
            self._content_depth = (self._content_depth or 0) + 1
            # Rebuild tag for content
            attr_str = ''
            for k, v in attrs:
                attr_str += f' {k}="{v}"'
            self.content_html += f'<{tag}{attr_str}>'

    def handle_endtag(self, tag):
        if self.in_posttitle_a and tag == 'a':
            self.in_posttitle_a = False
        if self.in_writer and tag == 'div':
            self.in_writer = False
        if self.in_postcontent:
            self._content_depth -= 1
            self.content_html += f'</{tag}>'
            if self._content_depth <= 0:
                self.in_postcontent = False

    def handle_data(self, data):
        if self.in_posttitle_a:
            self.title += data
        if self.in_writer and not self.date_raw:
            # Date appears as: نویسنده: آرام بهرامی - 1388/1/30
            match = re.search(r'[\d۰-۹]+/[\d۰-۹]+/[\d۰-۹]+', data)
            if match:
                self.date_raw = parse_persian_digits(match.group())
        if self.in_postcontent:
            self.content_html += html.escape(data)

    def handle_entityref(self, name):
        if self.in_postcontent:
            self.content_html += f'&{name};'

    def handle_charref(self, name):
        if self.in_postcontent:
            self.content_html += f'&#{name};'


def parse_post_file(filepath):
    """Parse a single post HTML file and return (title, date_str, content_html)."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()

    parser = PostParser()
    parser.feed(raw)

    title = parser.title.strip() or os.path.basename(filepath)
    date_str = parser.date_raw.strip()
    content = parser.content_html.strip()

    # Convert Jalali date to RFC 822
    pub_date = 'Mon, 01 Jan 2000 00:00:00 +0000'  # fallback
    if date_str:
        try:
            parts = date_str.split('/')
            jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
            gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
            dt = datetime(gy, gm, gd, 12, 0, 0)
            pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
        except Exception:
            pass

    return title, pub_date, content, date_str


def generate_rss(post_folder, base_url):
    base_url = base_url.rstrip('/')
    post_files = sorted(
        [f for f in os.listdir(post_folder) if f.endswith('.htm') or f.endswith('.html')],
        key=lambda x: int(re.sub(r'\D', '', x) or '0'),
        reverse=True  # newest first
    )

    print(f"Found {len(post_files)} post files.")

    items = []
    for fname in post_files:
        fpath = os.path.join(post_folder, fname)
        try:
            title, pub_date, content, jalali_date = parse_post_file(fpath)
            post_num = re.sub(r'\D', '', fname)
            link = f'{base_url}/post/{fname}'
            item = f"""  <item>
    <title><![CDATA[{title}]]></title>
    <link>{link}</link>
    <guid>{link}</guid>
    <pubDate>{pub_date}</pubDate>
    <description><![CDATA[{content}]]></description>
  </item>"""
            items.append((pub_date, item))
            print(f"  ✓ {fname}: {title[:40]} | {jalali_date}")
        except Exception as e:
            print(f"  ✗ {fname}: ERROR — {e}")

    # Sort by date descending
    items.sort(key=lambda x: x[0], reverse=True)
    items_xml = '\n'.join(i for _, i in items)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>عدسک</title>
    <link>{base_url}</link>
    <description>وبلاگ عدسک</description>
    <language>fa</language>
    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""

    output_path = os.path.join(os.path.dirname(post_folder), 'feed.xml')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(rss)

    print(f"\n✅ Done! RSS feed written to: {output_path}")
    print(f"   Upload feed.xml to your GitHub repo root.")
    print(f"   Then give Substack this URL: {base_url}/feed.xml")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    generate_rss(sys.argv[1], sys.argv[2])
