import * as d3 from 'https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm'
import { feature, mesh } from 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/+esm'
import { parseTraceroute, isPublic, checkPhysics, geolocate, KM_PER_RTT_MS } from './ipmap.js'

const still = matchMedia('(prefers-reduced-motion: reduce)').matches
const $ = s => document.querySelector(s)
const form = $('#intake'), input = $('#trace'), errorEl = $('#error'), result = $('#result')
const list = $('#hops'), canvas = $('#globe'), originNote = $('#origin-note')
const color = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const km = n => `${Math.round(n).toLocaleString('en')} km`
const ms = n => (n < 10 ? n.toFixed(1) : Math.round(n).toString())

// The bundled example was traced from Buenos Aires, so it must be checked from there, not from the visitor.
const EXAMPLE_ORIGIN = { lat: -34.6131, lon: -58.3772, city: 'Buenos Aires', country: 'AR', org: '' }
let origin = null // null = use the visitor's own location
let state = { me: null, hops: [], active: -1, packet: null }

// --- globe -----------------------------------------------------------------------------------

const ctx = canvas.getContext('2d')
const projection = d3.geoOrthographic().clipAngle(90).precision(0.4)
const path = d3.geoPath(projection, ctx)
const graticule = d3.geoGraticule10()
let world = null
let palette = {}

const loadWorld = () =>
  (world ??= fetch('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json')
    .then(r => r.json())
    .then(t => ({ land: feature(t, t.objects.land), borders: mesh(t, t.objects.countries, (a, b) => a !== b) })))

function resize() {
  const { width } = canvas.getBoundingClientRect()
  const dpr = devicePixelRatio || 1
  canvas.width = canvas.height = Math.round(width * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  projection.translate([width / 2, width / 2]).scale(width / 2 - 4)
  draw()
}

const pt = g => [g.lon, g.lat]
const located = () => state.hops.filter(h => h.geo && !h.impossible)
const routePoints = () => [state.me, ...located().map(h => h.geo)].filter(Boolean).map(pt)

function stroke(geo, style, width, dash = []) {
  ctx.beginPath(); path(geo)
  ctx.setLineDash(dash); ctx.lineWidth = width; ctx.strokeStyle = style; ctx.stroke(); ctx.setLineDash([])
}
function dot(coords, r, fill, ring) {
  path.pointRadius(r); ctx.beginPath(); path({ type: 'Point', coordinates: coords })
  if (fill) { ctx.fillStyle = fill; ctx.fill() }
  if (ring) { ctx.lineWidth = 2; ctx.strokeStyle = ring; ctx.stroke() }
}

function draw() {
  const w = canvas.width
  ctx.clearRect(0, 0, w, w)
  ctx.beginPath(); path({ type: 'Sphere' }); ctx.fillStyle = '#0a1d29'; ctx.fill()
  stroke(graticule, 'rgba(143,178,192,.08)', 1)
  if (world?.land) {
    ctx.beginPath(); path(world.land); ctx.fillStyle = palette.land; ctx.fill()
    stroke(world.borders, palette.edge, 0.6)
  }
  ctx.beginPath(); path({ type: 'Sphere' }); ctx.lineWidth = 1; ctx.strokeStyle = palette.edge; ctx.stroke()

  const pts = routePoints()
  if (pts.length > 1) stroke({ type: 'LineString', coordinates: pts }, palette.signal, 2.2)

  const active = state.hops[state.active]
  if (active?.impossible && state.me) {
    // Where the router really has to be: inside light's reach from you.
    const deg = active.reachKm / 111.2
    stroke(d3.geoCircle().center(pt(state.me)).radius(deg)(), palette.wrong, 1.5, [4, 5])
    stroke({ type: 'LineString', coordinates: [pt(state.me), pt(active.geo)] }, 'rgba(255,95,162,.45)', 1.2, [2, 6])
  }
  for (const h of state.hops) {
    if (!h.geo) continue
    if (h.impossible) dot(pt(h.geo), h === active ? 9 : 6, null, palette.wrong)
    else dot(pt(h.geo), h === active ? 8 : 4, palette.signal, h === active ? palette.ink : null)
  }
  if (state.me) dot(pt(state.me), 6, palette.ink, '#0a1d29')
  if (state.packet) dot(state.packet, 5, '#fff', palette.signal)
}

let flight = null
function flyTo(g) {
  if (!g) return
  const from = projection.rotate()
  const to = [-g.lon, -g.lat * 0.75, 0]
  flight?.stop()
  if (still) { projection.rotate(to); return draw() }
  const turn = d3.interpolate(from, to)
  flight = d3.timer(t => {
    const k = d3.easeCubicInOut(Math.min(1, t / 900))
    projection.rotate(turn(k)); draw()
    if (k === 1) flight.stop()
  })
}

// Drag to spin the globe.
canvas.addEventListener('pointerdown', e => {
  flight?.stop()
  canvas.setPointerCapture(e.pointerId)
  let last = [e.clientX, e.clientY]
  const move = ev => {
    const [lam, phi] = projection.rotate()
    const k = 75 / projection.scale()
    projection.rotate([lam + (ev.clientX - last[0]) * k, Math.max(-80, Math.min(80, phi - (ev.clientY - last[1]) * k))])
    last = [ev.clientX, ev.clientY]; draw()
  }
  canvas.addEventListener('pointermove', move)
  canvas.addEventListener('pointerup', () => canvas.removeEventListener('pointermove', move), { once: true })
})

// One packet runs the route once, after everything is located.
function sendPacket() {
  const pts = routePoints()
  if (still || pts.length < 2) return
  const legs = d3.pairs(pts).map(([a, b]) => d3.geoInterpolate(a, b))
  const timer = d3.timer(t => {
    const k = Math.min(1, t / (900 * legs.length ** 0.6))
    const i = Math.min(legs.length - 1, Math.floor(k * legs.length))
    state.packet = legs[i](k * legs.length - i)
    draw()
    if (k === 1) { timer.stop(); state.packet = null; draw() }
  })
}

// --- hop sections ----------------------------------------------------------------------------

function group(hops) {
  // Collapse runs of silent hops, and hops inside your own network, into single quiet rows.
  const rows = []
  for (const h of hops) {
    const kind = !h.ip ? 'silent' : !isPublic(h.ip) ? 'private' : 'public'
    const prev = rows.at(-1)
    if (kind === 'silent' && prev?.kind === 'silent') prev.hops.push(h)
    else rows.push({ kind, hops: [h] })
  }
  return rows
}

function el(tag, cls, text) {
  const e = document.createElement(tag)
  if (cls) e.className = cls
  if (text != null) e.textContent = text
  return e
}

function renderRows(rows) {
  list.replaceChildren()
  for (const row of rows) {
    const h = row.hops[0]
    const li = el('li', 'hop')
    li.dataset.hop = state.hops.indexOf(h)
    const head = el('div', 'hop-head')
    if (row.kind === 'silent') {
      const last = row.hops.at(-1)
      li.classList.add('quiet')
      head.append(el('span', null, row.hops.length > 1 ? `Hops ${h.n} to ${last.n}` : `Hop ${h.n}`))
      li.append(head, el('h2', 'hop-place', 'No reply'),
        el('p', 'hop-addr', row.hops.length > 1 ? 'These routers stayed quiet. Many drop traceroute probes on purpose.' : 'This router stayed quiet. Many drop traceroute probes on purpose.'))
    } else if (row.kind === 'private') {
      li.classList.add('quiet')
      head.append(el('span', null, `Hop ${h.n}`), rtt(h))
      li.append(head, el('h2', 'hop-place', 'Your network'), addr(h))
    } else {
      li.classList.add('pending')
      head.append(el('span', null, `Hop ${h.n}`), rtt(h))
      li.append(head, el('h2', 'hop-place', 'Locating'), addr(h))
      h.li = li
    }
    list.append(li)
  }
}

function rtt(h) {
  const s = el('span', 'hop-rtt', h.rtt == null ? '' : ms(h.rtt))
  if (h.rtt != null) s.append(el('small', null, 'ms'))
  return s
}

function addr(h) {
  const p = el('p', 'hop-addr')
  p.append(el('b', null, h.ip))
  if (h.host) p.append(` ${h.host}`)
  if (h.alternates.length) p.append(el('br'), `Also answered: ${h.alternates.join(', ')}`)
  return p
}

function fill(h) {
  const li = h.li
  li.classList.remove('pending')
  const place = li.querySelector('.hop-place')
  if (!h.geo) {
    place.textContent = 'Unknown'
    li.append(el('p', 'verdict', 'No location data for this address.'))
    return
  }
  place.textContent = h.geo.city || h.geo.country || 'Somewhere'
  if (h.geo.org) li.querySelector('.hop-addr').append(el('br'), h.geo.org)
  if (h.distanceKm == null) return

  li.classList.toggle('impossible', h.impossible)
  const scale = Math.max(h.reachKm, h.distanceKm) * 1.08
  const meter = el('div', 'meter')
  meter.style.setProperty('--reach', `${(h.reachKm / scale) * 100}%`)
  meter.style.setProperty('--dist', `${(h.distanceKm / scale) * 100}%`)
  meter.append(el('span', 'reach'), el('span', 'dist'))
  meter.setAttribute('role', 'img')
  meter.setAttribute('aria-label', `Light reach ${km(h.reachKm)}, claimed distance ${km(h.distanceKm)}`)
  const key = el('div', 'meter-key')
  key.append(el('span', null, `Light reach in ${ms(h.rtt)} ms: ${km(h.reachKm)}`), el('span', null, `Claimed: ${km(h.distanceKm)} away`))
  const verdict = h.impossible
    ? `Can't be in ${place.textContent}. A reply from ${km(h.distanceKm)} away takes at least ${Math.ceil(h.distanceKm / KM_PER_RTT_MS)} ms; this one took ${ms(h.rtt)} ms. The real router is inside the dashed circle.`
    : `Checks out: ${km(h.distanceKm)} away, and light covers ${km(h.reachKm)} in ${ms(h.rtt)} ms.`
  li.append(meter, key, el('p', 'verdict', verdict))
}

const observer = new IntersectionObserver(
  entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue
      const i = Number(e.target.dataset.hop)
      document.querySelectorAll('.hop.is-active').forEach(n => n.classList.remove('is-active'))
      e.target.classList.add('is-active')
      state.active = i
      const h = state.hops[i]
      // For a flagged hop, frame both you and the false location so the light-reach circle is in view.
      if (h?.impossible && state.me) {
        const [lon, lat] = d3.geoInterpolate(pt(state.me), pt(h.geo))(0.5)
        flyTo({ lon, lat })
      } else flyTo(h?.geo || state.me)
      draw()
    }
  },
  { rootMargin: '-45% 0px -45% 0px' }
)

// --- run -------------------------------------------------------------------------------------

async function pool(items, limit, fn) {
  const queue = [...items]
  await Promise.all(Array.from({ length: limit }, async () => { while (queue.length) await fn(queue.shift()) }))
}

async function map(text) {
  errorEl.hidden = true
  const hops = parseTraceroute(text)
  if (!hops.length) {
    errorEl.textContent = 'No hops found. Paste the full output of traceroute (macOS, Linux) or tracert (Windows).'
    errorEl.hidden = false
    return
  }
  const submit = form.querySelector('.primary')
  submit.disabled = true
  palette = { land: color('--land'), edge: color('--land-edge'), signal: color('--signal'), wrong: color('--wrong'), ink: color('--ink') }
  state = { me: null, hops, active: -1, packet: null }
  result.hidden = false
  renderRows(group(hops))
  resize()
  observer.disconnect()
  list.querySelectorAll('.hop').forEach(li => observer.observe(li))
  result.scrollIntoView({ behavior: still ? 'auto' : 'smooth' })

  loadWorld().then(w => { world = w; draw() })
  state.me = origin || (await geolocate())
  originNote.textContent = state.me
    ? `Distances measured from ${[state.me.city, state.me.country].filter(Boolean).join(', ')}${origin ? ', where this example was traced' : ', your approximate location. Paste a traceroute you ran from here'}.`
    : 'Your location could not be looked up, so the speed-of-light check is off.'
  flyTo(state.me)

  const publicHops = hops.filter(h => h.ip && isPublic(h.ip))
  let found = 0
  await pool(publicHops, 2, async h => {
    h.geo = await geolocate(h.ip)
    if (h.geo) found++
    checkPhysics(h, state.me)
    fill(h)
    draw()
  })
  submit.disabled = false
  if (publicHops.length && !found) {
    errorEl.textContent = "Couldn't reach the location services (ipwho.is, ipapi.is). Check your connection, or try again in a minute."
    errorEl.hidden = false
    form.scrollIntoView({ behavior: 'auto' })
    return
  }
  sendPacket()
}

form.addEventListener('submit', e => {
  e.preventDefault()
  origin = input.dataset.example === input.value ? EXAMPLE_ORIGIN : null
  map(input.value)
})

const loadExample = async () => {
  const text = await fetch('examples/google-from-buenos-aires.txt').then(r => r.text())
  input.value = input.dataset.example = text
  origin = EXAMPLE_ORIGIN
  map(text)
}
$('#example').addEventListener('click', loadExample)
if (location.hash === '#example') loadExample() // shareable demo link: .../ipmap/#example

new ResizeObserver(() => !result.hidden && resize()).observe(canvas)
