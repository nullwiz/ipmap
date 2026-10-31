"""ipmap: see where your packets actually go.

Runs (or reads) a traceroute, geolocates every public hop in one request, prints the route,
and draws it on a globe. Hops whose claimed location is physically impossible for their
round-trip time get flagged: light in fiber covers about 100 km per millisecond of RTT,
so a router "in California" that answers Buenos Aires in 15 ms is not in California.
"""

import argparse
import ipaddress
import json
import math
import re
import shutil
import subprocess
import sys
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Light in fiber travels ~200,000 km/s, so per ms of round trip a reply can come from at most ~100 km away.
KM_PER_RTT_MS = 100
# Slack for our own location being approximate (it's geolocated from our public IP too).
ORIGIN_SLACK_KM = 300

GEO_FIELDS = "status,message,query,country,countryCode,city,lat,lon,isp,org,as"


@dataclass
class Hop:
    n: int
    ip: Optional[str] = None  # first router that answered; None if the hop timed out
    host: Optional[str] = None
    rtts: List[float] = field(default_factory=list)
    alternates: List[str] = field(default_factory=list)  # other routers answering the same hop (load balancing)
    geo: Optional[dict] = None
    distance_km: Optional[float] = None
    impossible: bool = False

    @property
    def rtt(self):
        return min(self.rtts) if self.rtts else None

    @property
    def public(self):
        return self.ip is not None and ipaddress.ip_address(self.ip).is_global


# --- parsing ---------------------------------------------------------------------------------

HOP_LINE = re.compile(r"^\s*(\d+)\s+(.*)$")
RTT = re.compile(r"<?(\d+(?:\.\d+)?)\s*ms")


def _as_ip(token):
    try:
        return str(ipaddress.ip_address(token.strip("()[]")))
    except ValueError:
        return None


def parse_traceroute(text):
    """Parse traceroute (Linux/macOS) or tracert (Windows) output into ordered hops."""
    hops = []
    for line in text.splitlines():
        m = HOP_LINE.match(line)
        if not m:
            continue  # header ("traceroute to ...") or noise
        hop = Hop(n=int(m.group(1)))
        tokens = m.group(2).split()
        for i, tok in enumerate(tokens):
            ip = _as_ip(tok)
            if not ip:
                continue
            # "name (1.2.3.4)": the hostname sits right before the parenthesized IP
            prev = tokens[i - 1] if i else ""
            named = tok.startswith("(") and prev and not _as_ip(prev) and prev not in ("ms", "*")
            host = prev if named and prev != ip else None
            if hop.ip is None:
                hop.ip, hop.host = ip, host
            elif ip != hop.ip and ip not in hop.alternates:
                hop.alternates.append(ip)
        hop.rtts = [float(x) for x in RTT.findall(m.group(2))]
        hops.append(hop)
    return hops


# --- geolocation -----------------------------------------------------------------------------

def _get_json(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def geolocate(ips):
    """Batch lookup at ip-api.com (free tier: plain HTTP, up to 100 IPs per request)."""
    out = {}
    ips = list(dict.fromkeys(ips))
    for i in range(0, len(ips), 100):
        for g in _get_json(f"http://ip-api.com/batch?fields={GEO_FIELDS}", ips[i : i + 100]):
            if g.get("status") == "success":
                out[g["query"]] = g
    return out


def locate_me():
    g = _get_json(f"http://ip-api.com/json/?fields={GEO_FIELDS}")
    return g if g.get("status") == "success" else None


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def check_physics(hops, me):
    """Flag hops that would need faster-than-light replies to be where the database says."""
    for hop in hops:
        if not (hop.geo and me and hop.rtt is not None):
            continue
        hop.distance_km = haversine_km(me, hop.geo)
        hop.impossible = hop.distance_km > hop.rtt * KM_PER_RTT_MS + ORIGIN_SLACK_KM


def circle(center, radius_km, steps=90):
    """Points on the circle of the given ground distance around a lat/lon."""
    lat1, lon1, d = math.radians(center["lat"]), math.radians(center["lon"]), radius_km / 6371
    lats, lons = [], []
    for i in range(steps + 1):
        b = 2 * math.pi * i / steps
        lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
        lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
        lats.append(math.degrees(lat2))
        lons.append(math.degrees(lon2))
    return lats, lons


# --- output ----------------------------------------------------------------------------------

def where(g):
    if not g:
        return ""
    place = ", ".join(x for x in (g.get("city"), g.get("countryCode")) if x)
    owner = g.get("org") or g.get("isp") or ""
    return f"{place}  {owner}".strip()


def print_table(hops, me, out=sys.stdout):
    if me:
        print(f"From {where(me)} ({me['query']})\n", file=out)
    print(f"{'hop':>3}  {'rtt':>8}  {'address':<16}  location", file=out)
    for h in hops:
        if h.ip is None:
            print(f"{h.n:>3}  {'':>8}  {'*':<16}  no reply", file=out)
            continue
        rtt = f"{h.rtt:.1f} ms" if h.rtt is not None else ""
        note = where(h.geo) if h.geo else ("private network" if not h.public else "unknown")
        print(f"{h.n:>3}  {rtt:>8}  {h.ip:<16}  {note}", file=out)
        if h.impossible:
            print(
                f"{'':>31}  ! {h.distance_km:,.0f} km away but replied in {h.rtt:.1f} ms;"
                f" light only gets ~{h.rtt * KM_PER_RTT_MS:,.0f} km. This location is wrong.",
                file=out,
            )


def draw_map(hops, me, title, path):
    import plotly.graph_objects as go  # only needed for the map

    def hover(h):
        name = f"{h.host}<br>" if h.host else ""
        return f"<b>Hop {h.n}</b>  {h.ip}<br>{name}{where(h.geo)}<br>{h.rtt:.1f} ms"

    ok = [h for h in hops if h.geo and not h.impossible]
    bad = [h for h in hops if h.geo and h.impossible]
    route = ([(me["lat"], me["lon"], f"<b>You</b><br>{where(me)}")] if me else []) + [
        (h.geo["lat"], h.geo["lon"], hover(h)) for h in ok
    ]

    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=[p[0] for p in route], lon=[p[1] for p in route], text=[p[2] for p in route],
        mode="lines+markers", line=dict(width=2, color="#6cc0ac"),
        marker=dict(size=9, color="#6cc0ac", line=dict(width=1.5, color="#1d1e22")),
        hoverinfo="text", name="Route",
    ))
    if bad:
        fig.add_trace(go.Scattergeo(
            lat=[h.geo["lat"] for h in bad], lon=[h.geo["lon"] for h in bad], mode="markers",
            marker=dict(size=12, color="rgba(0,0,0,0)", line=dict(width=2, color="#ff8a3d")),
            text=[hover(h) + f"<br><b>Can't be here:</b> {h.distance_km:,.0f} km in {h.rtt:.1f} ms" for h in bad],
            hoverinfo="text", name="Claimed location (physically impossible)",
        ))
    if bad and me:
        # The fastest flagged hop gives the tightest bound: it must sit inside this circle around you.
        h = min(bad, key=lambda h: h.rtt)
        lats, lons = circle(me, h.rtt * KM_PER_RTT_MS)
        fig.add_trace(go.Scattergeo(
            lat=lats, lon=lons, mode="lines", line=dict(width=1.5, color="#ff8a3d", dash="dot"),
            hoverinfo="skip", name=f"Where hop {h.n} really is: within {h.rtt * KM_PER_RTT_MS:,.0f} km ({h.rtt:.1f} ms)",
        ))
    lat, lon = (route[-1][0], route[-1][1]) if route else (0, 0)
    fig.update_geos(
        projection_type="orthographic", projection_rotation=dict(lat=lat, lon=lon),
        showland=True, landcolor="#2b2d33", showocean=True, oceancolor="#1d1e22", showcountries=True,
        countrycolor="#44454b", coastlinecolor="#55565c", showframe=False, bgcolor="#1d1e22",
    )
    fig.update_layout(
        title=dict(text=title, font=dict(color="#ebe9e3", size=20), x=0.03),
        paper_bgcolor="#1d1e22", font=dict(color="#bdbbb2"), margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(x=0.03, y=0.04, bgcolor="rgba(0,0,0,0)"), height=760,
        hoverlabel=dict(bgcolor="#25262b", bordercolor="#44454b", font=dict(color="#ebe9e3")),
    )
    fig.write_html(path, include_plotlyjs="cdn", config={"displaylogo": False})
    return path


# --- running traceroute ----------------------------------------------------------------------

def run_traceroute(target):
    cmd = ["tracert", "-d", target] if sys.platform == "win32" else ["traceroute", "-w", "2", "-q", "2", target]
    if not shutil.which(cmd[0]):
        sys.exit(f"ipmap: {cmd[0]} not found. Install it, or save its output and use: ipmap -f FILE")
    print(f"Tracing {target}...", file=sys.stderr)
    lines = []
    # List args, no shell: the target reaches traceroute as a single argument.
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as p:
        for line in p.stdout:
            print(line, end="", file=sys.stderr)  # live progress; traceroute is slow
            lines.append(line)
    return "".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ipmap", description="See where your packets go, on a globe.")
    ap.add_argument("target", nargs="?", help="host to trace, e.g. google.com")
    ap.add_argument("-f", "--file", help="read saved traceroute output instead ('-' for stdin)")
    ap.add_argument("-o", "--output", help="where to write the map (default: ipmap-<target>.html)")
    ap.add_argument("--no-map", action="store_true", help="only print the table")
    ap.add_argument("--no-open", action="store_true", help="write the map but don't open a browser")
    args = ap.parse_args(argv)

    if args.file:
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
        label = args.target or (Path(args.file).stem if args.file != "-" else "trace")
    elif args.target:
        text, label = run_traceroute(args.target), args.target
    else:
        ap.error("give a host to trace, or -f FILE with saved traceroute output")

    hops = parse_traceroute(text)
    if not hops:
        sys.exit("ipmap: no hops found. Is this traceroute output?")

    try:
        geo = geolocate([h.ip for h in hops if h.public])
        me = locate_me()
    except OSError as e:
        sys.exit(f"ipmap: location lookup failed ({e}). Check your connection; ip-api.com allows 45 requests a minute.")
    for h in hops:
        h.geo = geo.get(h.ip)
    check_physics(hops, me)

    print(file=sys.stderr)
    print_table(hops, me)
    if args.no_map:
        return
    if not any(h.geo for h in hops):
        sys.exit("\nipmap: none of the hops could be located, so there's nothing to map.")
    path = Path(args.output or f"ipmap-{re.sub(r'[^A-Za-z0-9._-]', '_', label)}.html").resolve()
    draw_map(hops, me, f"Route to {label}", str(path))
    print(f"\nMap: {path}")
    if not args.no_open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
