import json
import math
import os
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np
import pandas as pd
import requests
from pyproj import Transformer
from shapely.geometry import LineString, Point
from sklearn.neighbors import BallTree
from tqdm import tqdm


def _read_pois(csv_path: str) -> List[Dict]:
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["longitude", "latitude"])
    records = df.to_dict(orient="records")
    pois = []
    for record in tqdm(records, desc="Processing POIs", unit="poi"):
        pois.append(
            {
                "id": record.get("id"),
                "name": record.get("name"),
                "longitude": float(record["longitude"]),
                "latitude": float(record["latitude"]),
            }
        )
    return pois


def _haversine_distance_m(a: Dict, b: Dict) -> float:
    lon1 = math.radians(a["longitude"])
    lat1 = math.radians(a["latitude"])
    lon2 = math.radians(b["longitude"])
    lat2 = math.radians(b["latitude"])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(h))
    return 6371000.0 * c


def _fetch_route_geometry(
    a: Dict,
    b: Dict,
    mapbox_token: str,
    profile: str = "walking",
) -> Tuple[List[List[float]], float, float]:
    base_url = "https://api.mapbox.com/directions/v5/mapbox"
    coordinates = f"{a['longitude']},{a['latitude']};{b['longitude']},{b['latitude']}"
    url = (
        f"{base_url}/{profile}/{coordinates}"
        "?alternatives=false&geometries=geojson&overview=full"
        f"&access_token={mapbox_token}"
    )
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    data = response.json()
    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("No routes returned by Mapbox Directions API")
    route = routes[0]
    geometry = route["geometry"]["coordinates"]
    distance = float(route.get("distance", 0.0))
    duration = float(route.get("duration", 0.0))
    return geometry, distance, duration


def _build_transformer() -> Transformer:
    return Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def _build_poi_graph_from_pois(
    pois: List[Dict],
    mapbox_token: str,
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> Tuple[List[Dict], List[Dict]]:
    transformer = _build_transformer()

    nodes = []
    for poi in tqdm(pois, desc="Building graph nodes", unit="node"):
        nodes.append(
            {
                "id": poi["name"],
                "name": poi["name"],
                "longitude": poi["longitude"],
                "latitude": poi["latitude"],
                "rag_unit_id": poi.get("rag_unit_id"),
                "rag_unit_name": poi.get("rag_unit_name"),
            }
        )

    # Build a BallTree to get k-NN candidate neighbors, instead of evaluating all O(n^2) pairs.
    n = len(pois)
    if n == 0:
        return nodes, []

    coords = np.array([[p["latitude"], p["longitude"]] for p in pois], dtype=float)
    coords_rad = np.radians(coords)
    tree = BallTree(coords_rad, metric="haversine")
    earth_radius_m = 6371000.0

    candidate_pairs = set()
    k = min(k_neighbors + 1, n)
    for i in range(n):
        dist, ind = tree.query(coords_rad[i : i + 1], k=k)
        for d, j in zip(dist[0][1:], ind[0][1:]):  # skip self at index 0
            distance_m = d * earth_radius_m
            if distance_m > max_pair_distance_m:
                continue
            if i < j:
                key = (i, j)
            else:
                key = (j, i)
            candidate_pairs.add(key)

    edges: List[Dict] = []
    edge_keys = set()

    candidate_pairs = list(candidate_pairs)
    pair_bar = tqdm(total=len(candidate_pairs), desc="Evaluating POI pairs", unit="pair")
    route_bar = tqdm(desc="Requesting routes", unit="route")

    for i, j in candidate_pairs:
        pair_bar.update(1)
        a = pois[i]
        b = pois[j]

        try:
            route_bar.update(1)
            geometry, distance, duration = _fetch_route_geometry(a, b, mapbox_token, profile)
        except Exception:
            continue

        # Build a projected line once per route for intermediate detection and splitting
        line_xy = [transformer.transform(lon, lat) for lon, lat in geometry]
        if len(line_xy) < 2:
            continue
        line = LineString(line_xy)

        # Precompute cumulative distances along the route in projected coordinates
        cumdist = [0.0]
        for idx in range(1, len(line_xy)):
            dx = line_xy[idx][0] - line_xy[idx - 1][0]
            dy = line_xy[idx][1] - line_xy[idx - 1][1]
            cumdist.append(cumdist[-1] + math.hypot(dx, dy))

        total_length_xy = cumdist[-1] if cumdist else 0.0

        # Find intermediate POIs whose vicinity intersects this route
        intermediate_infos = []
        for k_idx in range(len(pois)):
            if k_idx == i or k_idx == j:
                continue
            c = pois[k_idx]
            px, py = transformer.transform(c["longitude"], c["latitude"])
            point = Point(px, py)
            dist_xy = point.distance(line)
            if dist_xy <= vicinity_radius_m:
                pos = line.project(point)
                # Map the projection measure to the nearest vertex index
                nearest_idx = min(
                    range(len(cumdist)),
                    key=lambda idx: abs(cumdist[idx] - pos),
                )
                intermediate_infos.append((pos, nearest_idx, c))

        if not intermediate_infos:
            # No intermediate POIs detected: keep the direct edge
            key = frozenset((a["name"], b["name"]))
            if key not in edge_keys:
                edges.append(
                    {
                        "from": a["name"],
                        "to": b["name"],
                        "distance_m": distance,
                        "duration_s": duration,
                        "geometry": geometry,
                        "fallback": False,
                    }
                )
                edge_keys.add(key)
            continue

        # Split the route into segments A -> P1 -> ... -> Pn -> B
        # Order intermediates along the route
        intermediate_infos.sort(key=lambda t: t[0])
        # Chain: each element is (measure, index_on_route, poi_dict)
        chain = [(0.0, 0, a)] + intermediate_infos + [
            (total_length_xy, len(geometry) - 1, b)
        ]

        for s_info, e_info in zip(chain[:-1], chain[1:]):
            _, start_idx, poi_start = s_info
            _, end_idx, poi_end = e_info
            if end_idx <= start_idx:
                continue

            key = frozenset((poi_start["name"], poi_end["name"]))
            if key in edge_keys:
                continue

            # Extract sub-geometry for this segment
            segment_coords = geometry[start_idx : end_idx + 1]
            if not segment_coords:
                segment_coords = [
                    [poi_start["longitude"], poi_start["latitude"]],
                    [poi_end["longitude"], poi_end["latitude"]],
                ]
            else:
                # Ensure endpoints match POI coordinates
                segment_coords[0] = [
                    poi_start["longitude"],
                    poi_start["latitude"],
                ]
                segment_coords[-1] = [
                    poi_end["longitude"],
                    poi_end["latitude"],
                ]

            if total_length_xy > 0:
                segment_length_xy = cumdist[end_idx] - cumdist[start_idx]
                distance_m_segment = distance * (segment_length_xy / total_length_xy)
            else:
                distance_m_segment = _haversine_distance_m(poi_start, poi_end)

            edges.append(
                {
                    "from": poi_start["name"],
                    "to": poi_end["name"],
                    "distance_m": distance_m_segment,
                    "duration_s": duration,
                    "geometry": segment_coords,
                    "fallback": False,
                }
            )
            edge_keys.add(key)

    pair_bar.close()
    route_bar.close()

    _ensure_graph_connectivity(nodes, edges, mapbox_token, profile)

    return nodes, edges


def build_poi_graph_from_csv(
    csv_path: str,
    mapbox_token: str,
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> Tuple[List[Dict], List[Dict]]:
    pois = _read_pois(csv_path)
    return _build_poi_graph_from_pois(
        pois=pois,
        mapbox_token=mapbox_token,
        profile=profile,
        vicinity_radius_m=vicinity_radius_m,
        max_pair_distance_m=max_pair_distance_m,
        k_neighbors=k_neighbors,
    )


def build_poi_graph_from_dataframe(
    df: pd.DataFrame,
    mapbox_token: str,
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> Tuple[List[Dict], List[Dict]]:
    required = {"name", "longitude", "latitude"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    clean_df = df.dropna(subset=["longitude", "latitude"])
    records = clean_df.to_dict(orient="records")
    pois: List[Dict] = []
    for record in tqdm(records, desc="Processing POIs from DataFrame", unit="poi"):
        pois.append(
            {
                "id": record.get("id"),
                "name": record.get("name"),
                "longitude": float(record["longitude"]),
                "latitude": float(record["latitude"]),
                "rag_unit_id": record.get("rag_unit_id"),
                "rag_unit_name": record.get("rag_unit_name"),
            }
        )

    return _build_poi_graph_from_pois(
        pois=pois,
        mapbox_token=mapbox_token,
        profile=profile,
        vicinity_radius_m=vicinity_radius_m,
        max_pair_distance_m=max_pair_distance_m,
        k_neighbors=k_neighbors,
    )


def _ensure_graph_connectivity(
    nodes: List[Dict],
    edges: List[Dict],
    mapbox_token: str,
    profile: str,
) -> None:
    if not nodes:
        return

    node_by_name = {n["name"]: n for n in nodes}

    G = nx.Graph()
    for node in nodes:
        G.add_node(node["name"])
    for edge in edges:
        G.add_edge(edge["from"], edge["to"])

    existing_pairs = {
        frozenset((edge["from"], edge["to"])) for edge in edges
    }

    for node_name in list(G.nodes()):
        if G.degree(node_name) > 0:
            continue
        poi = node_by_name.get(node_name)
        if not poi:
            continue

        best_other = None
        best_dist = float("inf")
        for other_name, other_poi in node_by_name.items():
            if other_name == node_name:
                continue
            d = _haversine_distance_m(poi, other_poi)
            if d < best_dist:
                best_dist = d
                best_other = other_name

        if best_other is None:
            continue

        pair_key = frozenset((node_name, best_other))
        if pair_key in existing_pairs:
            continue

        a = poi
        b = node_by_name[best_other]
        try:
            geometry, distance, duration = _fetch_route_geometry(a, b, mapbox_token, profile)
        except Exception:
            geometry = [
                [a["longitude"], a["latitude"]],
                [b["longitude"], b["latitude"]],
            ]
            distance = best_dist
            duration = 0.0

        edges.append(
            {
                "from": a["name"],
                "to": b["name"],
                "distance_m": distance,
                "duration_s": duration,
                "geometry": geometry,
                "fallback": True,
            }
        )
        G.add_edge(a["name"], b["name"])
        existing_pairs.add(pair_key)

    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return

    components.sort(key=len, reverse=True)
    main_component = components[0]

    for comp in components[1:]:
        best_pair = None
        best_dist = float("inf")
        for name_u in comp:
            poi_u = node_by_name.get(name_u)
            if not poi_u:
                continue
            for name_v in main_component:
                poi_v = node_by_name.get(name_v)
                if not poi_v:
                    continue
                d = _haversine_distance_m(poi_u, poi_v)
                if d < best_dist:
                    best_dist = d
                    best_pair = (name_u, name_v)

        if not best_pair:
            continue

        u_name, v_name = best_pair
        pair_key = frozenset(best_pair)
        if pair_key in existing_pairs:
            continue

        a = node_by_name[u_name]
        b = node_by_name[v_name]

        try:
            geometry, distance, duration = _fetch_route_geometry(a, b, mapbox_token, profile)
        except Exception:
            geometry = [
                [a["longitude"], a["latitude"]],
                [b["longitude"], b["latitude"]],
            ]
            distance = best_dist
            duration = 0.0

        edges.append(
            {
                "from": a["name"],
                "to": b["name"],
                "distance_m": distance,
                "duration_s": duration,
                "geometry": geometry,
                "fallback": True,
            }
        )
        G.add_edge(a["name"], b["name"])
        existing_pairs.add(pair_key)


def generate_map_html(
    nodes: List[Dict],
    edges: List[Dict],
    mapbox_token: str,
    output_path: str,
) -> None:
    node_features = []
    for node in nodes:
        node_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node["longitude"], node["latitude"]],
                },
                "properties": {
                    "id": node["id"],
                    "name": node["name"],
                },
            }
        )

    edge_features = []
    for edge in edges:
        edge_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": edge["geometry"],
                },
                "properties": {
                    "from": edge["from"],
                    "to": edge["to"],
                    "distance_m": edge["distance_m"],
                    "duration_s": edge["duration_s"],
                },
            }
        )

    nodes_geojson = {"type": "FeatureCollection", "features": node_features}
    edges_geojson = {"type": "FeatureCollection", "features": edge_features}

    if not nodes:
        center = [103.8198, 1.3521]
    else:
        lon_values = [node["longitude"] for node in nodes]
        lat_values = [node["latitude"] for node in nodes]
        center = [sum(lon_values) / len(lon_values), sum(lat_values) / len(lat_values)]

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>POI Graph on Mapbox</title>
  <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
  <script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
  <link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet" />
  <style>
    body {{ margin: 0; padding: 0; }}
    #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    mapboxgl.accessToken = {json.dumps(mapbox_token)};
    const nodesGeoJSON = {json.dumps(nodes_geojson)};
    const edgesGeoJSON = {json.dumps(edges_geojson)};

    const map = new mapboxgl.Map({{
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v12',
      center: {json.dumps(center)},
      zoom: 14
    }});

    map.on('load', () => {{
      map.addSource('pois', {{
        type: 'geojson',
        data: nodesGeoJSON
      }});

      map.addSource('routes', {{
        type: 'geojson',
        data: edgesGeoJSON
      }});

      map.addLayer({{
        id: 'routes-layer',
        type: 'line',
        source: 'routes',
        paint: {{
          'line-color': '#ff7f0e',
          'line-width': 3
        }}
      }});

      map.addLayer({{
        id: 'poi-layer',
        type: 'circle',
        source: 'pois',
        paint: {{
          'circle-radius': 5,
          'circle-color': '#1f77b4',
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff'
        }}
      }});

      map.addLayer({{
        id: 'poi-labels',
        type: 'symbol',
        source: 'pois',
        layout: {{
          'text-field': ['get', 'name'],
          'text-size': 11,
          'text-offset': [0, 1.0],
          'text-anchor': 'top'
        }},
        paint: {{
          'text-color': '#111111',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1
        }}
      }});

      if (nodesGeoJSON.features.length > 0) {{
        const coordinates = nodesGeoJSON.features.map(f => f.geometry.coordinates);
        const bounds = coordinates.reduce(
          (b, coord) => b.extend(coord),
          new mapboxgl.LngLatBounds(coordinates[0], coordinates[0])
        );
        map.fitBounds(bounds, {{ padding: 40 }});
      }}
    }});
  </script>
</body>
</html>
"""

    directory = os.path.dirname(output_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def build_and_save_graph_html(
    csv_path: str,
    mapbox_token: str,
    output_html: str = "poi_graph_mapbox.html",
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> None:
    nodes, edges = build_poi_graph_from_csv(
        csv_path=csv_path,
        mapbox_token=mapbox_token,
        profile=profile,
        vicinity_radius_m=vicinity_radius_m,
        max_pair_distance_m=max_pair_distance_m,
        k_neighbors=k_neighbors,
    )
    generate_map_html(nodes, edges, mapbox_token, output_html)


def _require_mapbox_token(explicit_token: str | None = None) -> str:
    """
    Resolve the Mapbox access token, preferring an explicit value and
    falling back to the MAPBOX_ACCESS_TOKEN environment variable.
    """
    token = explicit_token or os.environ.get("MAPBOX_ACCESS_TOKEN") or ""
    if not token:
        raise RuntimeError("MAPBOX_ACCESS_TOKEN environment variable not set")
    return token


def build_mapbox_poi_graph(
    poi_df: pd.DataFrame,
    mapbox_token: str | None = None,
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Build the Mapbox-based POI graph from an in-memory POI dataframe.

    The dataframe must contain at least: 'name', 'longitude', 'latitude'.
    """
    token = _require_mapbox_token(mapbox_token)
    nodes, edges = build_poi_graph_from_dataframe(
        df=poi_df,
        mapbox_token=token,
        profile=profile,
        vicinity_radius_m=vicinity_radius_m,
        max_pair_distance_m=max_pair_distance_m,
        k_neighbors=k_neighbors,
    )
    return nodes, edges


def build_mapbox_poi_graph_html(
    poi_df: pd.DataFrame,
    output_path: str,
    mapbox_token: str | None = None,
    profile: str = "walking",
    vicinity_radius_m: float = 40.0,
    max_pair_distance_m: float = 4000.0,
    k_neighbors: int = 5,
) -> Dict[str, List[Dict]]:
    """
    Build the Mapbox-based POI graph and write it as an HTML file suitable
    for rendering by Flask/Jinja templates.

    Returns a dict with 'nodes' and 'edges' for optional in-memory use.
    """
    token = _require_mapbox_token(mapbox_token)
    nodes, edges = build_mapbox_poi_graph(
        poi_df=poi_df,
        mapbox_token=token,
        profile=profile,
        vicinity_radius_m=vicinity_radius_m,
        max_pair_distance_m=max_pair_distance_m,
        k_neighbors=k_neighbors,
    )
    generate_map_html(nodes, edges, token, output_path)
    return {"nodes": nodes, "edges": edges}


def build_networkx_graph(nodes: List[Dict], edges: List[Dict]) -> nx.Graph:
    """
    Construct a NetworkX graph from serialized node/edge data.
    """
    G = nx.Graph()
    for node in nodes:
        name = node["name"]
        G.add_node(
            name,
            longitude=node.get("longitude"),
            latitude=node.get("latitude"),
            metadata=node,
        )

    for edge in edges:
        u = edge["from"]
        v = edge["to"]
        distance_m = edge.get("distance_m", 0.0)
        G.add_edge(
            u,
            v,
            weight=distance_m,
            distance_m=distance_m,
            duration_s=edge.get("duration_s"),
            geometry=edge.get("geometry"),
            fallback=edge.get("fallback", False),
        )
    return G


def _build_poi_lookup(poi_df: pd.DataFrame) -> Dict[str, Dict]:
    records = poi_df.fillna("").to_dict(orient="records")
    return {record["name"]: record for record in records if record.get("name")}


def _build_route_geojson(segments: List[Dict]) -> Dict:
    features = []
    for seg in segments:
        coords = seg.get("geometry")
        if not coords:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "from": seg.get("from"),
                    "to": seg.get("to"),
                    "distance_m": seg.get("distance_m"),
                    "duration_s": seg.get("duration_s"),
                    "fallback": seg.get("fallback", False),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _shortest_path_with_segments(
    G: nx.Graph,
    start: str,
    end: str,
) -> Tuple[List[str], List[Dict], float]:
    path = nx.shortest_path(G, start, end, weight="distance_m")
    segments = []
    total_distance = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = G[u][v]
        distance_m = data.get("distance_m") or data.get("weight") or 0.0
        total_distance += distance_m
        segments.append(
            {
                "from": u,
                "to": v,
                "distance_m": distance_m,
                "duration_s": data.get("duration_s"),
                "geometry": data.get("geometry"),
                "fallback": data.get("fallback", False),
            }
        )
    return path, segments, total_distance


def plan_route_through_pois(
    poi_names: List[str],
    nodes: List[Dict],
    edges: List[Dict],
    poi_df: pd.DataFrame,
) -> Dict:
    """
    Compute an ordered walking route that visits the provided POIs (in order)
    using the pre-built Mapbox graph. Also returns any intermediate POIs
    encountered along the shortest paths between each requested POI pair.
    """
    if len(poi_names) < 2:
        raise ValueError("At least two POIs are required to build a route.")

    poi_lookup = _build_poi_lookup(poi_df)
    available_nodes = {node["name"] for node in nodes}
    missing = [name for name in poi_names if name not in available_nodes]
    if missing:
        raise ValueError(f"POIs not found in graph: {', '.join(missing)}")

    G = build_networkx_graph(nodes, edges)

    route_nodes: List[str] = []
    segments: List[Dict] = []
    total_distance = 0.0

    for start, end in zip(poi_names[:-1], poi_names[1:]):
        try:
            path, segs, dist = _shortest_path_with_segments(G, start, end)
        except nx.NetworkXNoPath:
            raise ValueError(f"No path found between '{start}' and '{end}'.")

        if not route_nodes:
            route_nodes.extend(path)
        else:
            route_nodes.extend(path[1:])
        segments.extend(segs)
        total_distance += dist

    requested_set = set(poi_names)
    passed_pois = []
    seen = set()
    for node_name in route_nodes:
        if node_name in requested_set or node_name in seen:
            continue
        seen.add(node_name)
        passed_pois.append(
            {
                "name": node_name,
                "details": poi_lookup.get(node_name, {"name": node_name}),
            }
        )

    route_details = [
        {"name": node, "details": poi_lookup.get(node, {"name": node})}
        for node in route_nodes
    ]

    requested_details = [
        {"name": node, "details": poi_lookup.get(node, {"name": node})}
        for node in poi_names
    ]

    return {
        "route_nodes": route_nodes,
        "route_details": route_details,
        "segments": segments,
        "total_distance_m": total_distance,
        "requested_pois": requested_details,
        "passed_pois": passed_pois,
        "route_geojson": _build_route_geojson(segments),
    }


def suggest_waypoint_pois(
    start_poi: str,
    end_poi: str,
    nodes: List[Dict],
    edges: List[Dict],
    poi_df: pd.DataFrame,
    categories: List[str] | None = None,
    tags: List[str] | None = None,
    max_detour_m: float = 800.0,
    max_results: int = 3,
) -> Dict:
    """
    Suggest POIs that lie "along the way" between start and end using the graph.
    If no POIs meet the detour threshold, include the closest detour as fallback.
    """
    categories = [c.lower() for c in (categories or []) if c]
    tags = [t.lower() for t in (tags or []) if t]

    poi_lookup = _build_poi_lookup(poi_df)
    available_nodes = {node["name"] for node in nodes}
    for poi in (start_poi, end_poi):
        if poi not in available_nodes:
            raise ValueError(f"POI '{poi}' not found in graph.")

    G = build_networkx_graph(nodes, edges)

    try:
        base_path, base_segments, base_distance = _shortest_path_with_segments(G, start_poi, end_poi)
    except nx.NetworkXNoPath:
        raise ValueError(f"No path found between '{start_poi}' and '{end_poi}'.")

    df = poi_df.copy()
    if categories:
        df = df[df["category"].str.lower().isin(categories)]
    if tags and "tags" in df.columns:
        df = df[df["tags"].astype(str).str.lower().apply(lambda x: any(tag in x for tag in tags))]

    df = df[df["name"].isin(available_nodes)]
    df = df[(df["name"] != start_poi) & (df["name"] != end_poi)]

    candidates = []
    for _, row in df.iterrows():
        poi_name = row["name"]
        try:
            path_start, seg_start, dist_start = _shortest_path_with_segments(G, start_poi, poi_name)
            path_end, seg_end, dist_end = _shortest_path_with_segments(G, poi_name, end_poi)
        except nx.NetworkXNoPath:
            continue

        detour = (dist_start + dist_end) - base_distance
        total_route = path_start[:-1] + path_end
        segments = seg_start + seg_end

        candidates.append(
            {
                "poi": {"name": poi_name, "details": poi_lookup.get(poi_name, {"name": poi_name})},
                "detour_m": detour,
                "total_distance_m": dist_start + dist_end,
                "route_nodes": total_route,
                "segments": segments,
                "route_geojson": _build_route_geojson(segments),
            }
        )

    if not candidates:
        return {
            "base_route": {
                "route_nodes": base_path,
                "segments": base_segments,
                "total_distance_m": base_distance,
                "route_geojson": _build_route_geojson(base_segments),
            },
            "candidates": [],
            "fallback": None,
        }

    candidates.sort(key=lambda c: c["detour_m"])
    filtered = [c for c in candidates if c["detour_m"] <= max_detour_m]
    fallback = candidates[0]
    return {
        "base_route": {
            "route_nodes": base_path,
            "segments": base_segments,
            "total_distance_m": base_distance,
            "route_geojson": _build_route_geojson(base_segments),
        },
        "candidates": filtered[:max_results] if filtered else [],
        "fallback": fallback if not filtered else None,
    }
