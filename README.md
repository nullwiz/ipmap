# ipmap

**Where did your packets go?** Paste a traceroute and follow every hop around a globe, with a
speed-of-light check on where each router claims to be.

**Try it:** https://nullwiz.github.io/ipmap/ ([demo with an example route](https://nullwiz.github.io/ipmap/#example))

## Why the speed of light

IP location databases are often wrong, especially for big networks like Google, which many
databases place in Mountain View no matter where the router really is. ipmap catches this with physics:
light in fiber travels about 200,000 km/s, so in a round trip of *t* ms a reply can come from at most
about *t* × 100 km away.

The example in this repo was traced from Buenos Aires. One database says hop 8 is in Mountain View,
10,360 km away, yet it replied in 21 ms. A reply from Mountain View needs at least 104 ms. That
router is in or near Buenos Aires, and ipmap draws the circle it has to be in.

## Use it

1. Run `traceroute google.com` (macOS, Linux) or `tracert google.com` (Windows).
2. Paste everything it prints into https://nullwiz.github.io/ipmap/.
3. Scroll through the hops. The globe follows along.

Everything runs in your browser. To find locations, public hop addresses (and your own, as the
starting point) are looked up at [ipwho.is](https://ipwho.is), or [ipapi.is](https://ipapi.is) as a
fallback. Distances are measured from your current location, so paste a traceroute you ran from
where you are now.

## Command line

The same idea is also available as a CLI, which runs traceroute for you:

```sh
uv tool install git+https://github.com/nullwiz/ipmap   # or: pip install git+https://github.com/nullwiz/ipmap
ipmap google.com                  # trace, print the route, open a map
ipmap -f trace.txt --no-map       # read saved output, table only
traceroute example.com | ipmap -f -
```

The CLI uses [ip-api.com](https://ip-api.com)'s free batch endpoint, which is plain HTTP.

## Develop

No build step. Serve the folder and open it:

```sh
python3 -m http.server 8000      # then visit http://localhost:8000/#example
node --test                      # web core: parser, physics, provider fallback
uv run --with plotly --with pytest pytest   # CLI
```

Files:

- `ipmap.js`: parsing, lookups and the physics check, with no DOM code.
- `app.js`: the globe (d3, drawn on a canvas) and the hop sections.
- `ipmap.py`: the CLI.

GitHub Pages serves the repo root as-is.
