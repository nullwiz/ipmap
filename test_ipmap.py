from pathlib import Path

from ipmap import Hop, check_physics, parse_traceroute

SAMPLE = (Path(__file__).parent / "examples" / "google-from-buenos-aires.txt").read_text()


def test_parses_hops_in_order_with_timeouts_and_alternates():
    hops = parse_traceroute(SAMPLE)
    assert [h.n for h in hops] == list(range(1, 13))
    assert hops[0].ip == "172.21.192.1" and not hops[0].public  # private, never sent for lookup
    assert hops[2].ip is None and hops[2].rtts == []  # "* * *"
    assert hops[7].ip == "72.14.194.198" and hops[7].rtt == 21.010
    assert hops[9].ip == "142.251.239.148"
    assert hops[9].alternates == ["142.251.239.146", "142.251.61.46"]
    assert hops[11].alternates == ["142.251.133.46"] and hops[11].rtt == 13.924


def test_reads_hostnames_and_windows_tracert():
    hops = parse_traceroute(" 1  eze10s02-in-f14.1e100.net (142.251.133.46)  15.1 ms")
    assert (hops[0].ip, hops[0].host) == ("142.251.133.46", "eze10s02-in-f14.1e100.net")
    win = parse_traceroute("  1    <1 ms    <1 ms    <1 ms  192.168.0.1\n  2     *        *        *     Request timed out.")
    assert win[0].ip == "192.168.0.1" and win[0].rtt == 1.0 and win[1].ip is None


def test_flags_locations_faster_than_light():
    buenos_aires = {"lat": -34.6, "lon": -58.4}
    near = Hop(1, "8.8.8.8", rtts=[15.0], geo={"lat": -34.8, "lon": -58.5})  # ~25 km, fine
    california = Hop(2, "8.8.4.4", rtts=[15.0], geo={"lat": 37.4, "lon": -122.1})  # ~10,000 km in 15 ms
    check_physics([near, california], buenos_aires)
    assert not near.impossible
    assert california.impossible and california.distance_km > 9000
