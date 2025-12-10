import os

from helpers.poi_graph_mapbox import build_and_save_graph_html


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    csv_default = os.path.join(here, "sentosa_with_tags.csv")
    token = os.environ.get("MAPBOX_ACCESS_TOKEN") or ""
    if not token:
        raise RuntimeError("Set MAPBOX_ACCESS_TOKEN environment variable before running this script.")
    output = os.path.join(here, "poi_graph_mapbox.html")
    build_and_save_graph_html(csv_default, token, output_html=output)
    print(f"POI graph HTML written to: {output}")

