// ipmap core: parse traceroute output, look up hop locations, and check them against the speed of light.
// No DOM here, so it runs in the browser and under `node --test`.

// Light in fiber travels ~200,000 km/s: per ms of round trip, a reply can come from at most ~100 km away.
export const KM_PER_RTT_MS = 100
// Slack for our own location being approximate (it's looked up from our public IP too).
export const ORIGIN_SLACK_KM = 300

const V4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/

export function asIp(token) {
  const t = token.replace(/^[([]+|[)\],]+$/g, '')
  if (V4.test(t)) return t
  if (t.includes(':') && /^[0-9a-f:.]+$/i.test(t)) {
    try {
      return new URL(`http://[${t}]/`).hostname.slice(1, -1) // the URL parser validates IPv6
    } catch {}
  }
  return null
}

// Private, loopback, link-local, CGNAT and multicast addresses never leave your network; don't look them up.
export function isPublic(ip) {
  if (!ip) return false
  if (ip.includes(':')) return !/^(::1?$|f[cd]|fe[89ab])/i.test(ip)
  const [a, b] = ip.split('.').map(Number)
  return !(
    a === 0 || a === 10 || a === 127 || a >= 224 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168)
  )
}

const HOP_LINE = /^\s*(\d+)\s+(.*)$/
const RTT = /<?(\d+(?:\.\d+)?)\s*ms/g

// Parse traceroute (Linux/macOS) or tracert (Windows) output into ordered hops.
export function parseTraceroute(text) {
  const hops = []
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(HOP_LINE)
    if (!m) continue // header ("traceroute to ...") or noise
    const hop = { n: Number(m[1]), ip: null, host: null, alternates: [], rtts: [] }
    const tokens = m[2].split(/\s+/)
    tokens.forEach((tok, i) => {
      const ip = asIp(tok)
      if (!ip) return
      // "name (1.2.3.4)": the hostname sits right before the parenthesized IP
      const prev = tokens[i - 1]
      const host = tok.startsWith('(') && prev && !asIp(prev) && prev !== 'ms' && prev !== '*' ? prev : null
      if (!hop.ip) Object.assign(hop, { ip, host })
      else if (ip !== hop.ip && !hop.alternates.includes(ip)) hop.alternates.push(ip)
    })
    hop.rtts = [...m[2].matchAll(RTT)].map(r => Number(r[1]))
    hop.rtt = hop.rtts.length ? Math.min(...hop.rtts) : null
    hops.push(hop)
  }
  return hops
}

export function haversineKm(a, b) {
  const r = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * r) / 2) ** 2 +
    Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

// Fill in distance and whether the claimed location needs a faster-than-light reply.
export function checkPhysics(hop, me) {
  if (!hop.geo || !me || hop.rtt == null) return hop
  hop.distanceKm = haversineKm(me, hop.geo)
  hop.reachKm = hop.rtt * KM_PER_RTT_MS
  hop.impossible = hop.distanceKm > hop.reachKm + ORIGIN_SLACK_KM
  return hop
}

// Look up an IP's location ('' = the visitor's own IP). Two free HTTPS providers that allow
// browser requests; the second is a fallback when the first is down or rate-limited.
const PROVIDERS = [
  ip => [`https://ipwho.is/${ip}`, d => d.success && {
    ip: d.ip, lat: d.latitude, lon: d.longitude, city: d.city, country: d.country_code,
    org: d.connection?.org || d.connection?.isp || ''
  }],
  ip => [`https://api.ipapi.is/${ip ? `?q=${ip}` : ''}`, d => ({
    ip: d.ip, lat: d.lat ?? d.location?.latitude, lon: d.lon ?? d.location?.longitude,
    city: d.city ?? d.location?.city, country: d.location?.country_code ?? d.country,
    org: (typeof d.company === 'string' ? d.company : d.company?.name) || ''
  })]
]

export async function geolocate(ip = '', fetchImpl = fetch) {
  for (const provider of PROVIDERS) {
    const [url, read] = provider(ip)
    try {
      const res = await fetchImpl(url)
      if (!res.ok) continue
      const g = read(await res.json())
      if (g && Number.isFinite(g.lat) && Number.isFinite(g.lon)) return g
    } catch {}
  }
  return null
}
