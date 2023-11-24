# -*- coding: utf-8 -*-
"""
Updated on: [Your update date]
@author: [Your name]
"""

import json
import requests
import ipaddress
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import argparse


def fetch_ip_data(ip):
    """
    Fetch IP data from the API.
    """
    url = f"http://ip-api.com/json/{ip}?fields=country,city,lat,lon"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return json.loads(response.text)
    except requests.RequestException as e:
        print(f"Error fetching data for IP {ip}: {e}")
        return None


def parse_trace_route(file):
    """
    Parse trace route from a file.
    """
    ip_list = []
    with open(file, "r") as f:
        for line in f:
            # Extract and validate IP addresses
            line = line.translate(str.maketrans("", "", "()"))
            for part in line.split():
                try:
                    ip = ipaddress.ip_address(part)
                    if str(ip) not in ip_list:
                        ip_list.append(str(ip))
                except ValueError:
                    continue
    return ip_list[1:]  # Skip the first local hop


def main(trace_route_file):
    ip_list = parse_trace_route(trace_route_file)
    lat_list, lon_list = [], []

    for ip in ip_list:
        data = fetch_ip_data(ip)
        if data:
            lat_list.append(data["lat"])
            lon_list.append(data["lon"])

    # Create a scatter geo map
    fig = make_subplots(rows=1, cols=1, specs=[[{"type": "scattergeo"}]])

    fig.add_trace(
        go.Scattergeo(
            lon=lon_list,
            lat=lat_list,
            mode="markers+lines",
            marker=dict(size=5, color="red"),
        )
    )

    fig.update_layout(
        title="IP Trace Route Visualization",
        geo=dict(projection_type="orthographic"),
        showlegend=False,
    )

    fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="IP Trace Route Visualization."
    )
    parser.add_argument(
        "trace_route_file", type=str, help="File containing trace route data."
    )
    args = parser.parse_args()
    main(args.trace_route_file)
