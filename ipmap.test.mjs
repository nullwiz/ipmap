import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parseTraceroute, isPublic, checkPhysics, geolocate } from './ipmap.js'

const sample = readFileSync(new URL('./examples/google-from-buenos-aires.txt', import.meta.url), 'utf8')

test('parses hops in order, with timeouts and load-balanced alternates', () => {
  const hops = parseTraceroute(sample)
  assert.deepEqual(hops.map(h => h.n), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
  assert.equal(hops[0].ip, '172.21.192.1')
  assert.equal(isPublic(hops[0].ip), false)
  assert.equal(hops[2].ip, null)
  assert.equal(hops[7].ip, '72.14.194.198')
  assert.equal(hops[7].rtt, 21.01)
  assert.deepEqual(hops[9].alternates, ['142.251.239.146', '142.251.61.46'])
  assert.equal(hops[11].rtt, 13.924)
})

test('reads hostnames, Windows tracert and IPv6', () => {
  const [named] = parseTraceroute(' 1  eze10s02-in-f14.1e100.net (142.251.133.46)  15.1 ms')
  assert.equal(named.host, 'eze10s02-in-f14.1e100.net')
  const win = parseTraceroute('  1    <1 ms    <1 ms    <1 ms  192.168.0.1\n  2     *        *        *     Request timed out.')
  assert.equal(win[0].ip, '192.168.0.1')
  assert.equal(win[0].rtt, 1)
  assert.equal(win[1].ip, null)
  const [v6] = parseTraceroute(' 3  2001:4860:0:1::1  12.3 ms')
  assert.equal(v6.ip, '2001:4860:0:1::1')
  assert.ok(isPublic(v6.ip))
  assert.ok(!isPublic('fe80::1') && !isPublic('100.64.0.1') && isPublic('8.8.8.8'))
})

test('flags locations that would need faster-than-light replies', () => {
  const buenosAires = { lat: -34.6, lon: -58.4 }
  const near = checkPhysics({ rtt: 15, geo: { lat: -34.8, lon: -58.5 } }, buenosAires)
  const california = checkPhysics({ rtt: 15, geo: { lat: 37.4, lon: -122.1 } }, buenosAires)
  assert.equal(near.impossible, false)
  assert.equal(california.impossible, true)
  assert.ok(california.distanceKm > 9000)
})

test('falls back to the second provider when the first fails', async () => {
  const fake = async url =>
    url.includes('ipwho.is')
      ? { ok: false }
      : { ok: true, json: async () => ({ ip: '8.8.8.8', lat: 37.4, lon: -122.1, city: 'Mountain View', country: 'United States', company: 'Google LLC' }) }
  const g = await geolocate('8.8.8.8', fake)
  assert.equal(g.city, 'Mountain View')
  assert.equal(g.org, 'Google LLC')
})
