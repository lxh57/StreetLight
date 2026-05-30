from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

API_URL = "https://nervous-commotion-countdown.ngrok-free.dev/api/streetlights"
API_PARAMS = {
    "limit": 500,
    "offset": 0,
    "sequence_id": None,
}
OUTPUT_HTML = Path(__file__).resolve().parent / "street_lights_output.html"
TEMPLATE_HTML = Path(__file__).resolve().parent / "street_lights.html"
INPUT_JSON_PATH: Optional[Path] = Path(__file__).resolve().parent / "streetlights_new2000.json"
SORT_ROUTE_BY_CAPTURED_AT = True
TIMEOUT_SECONDS = 60
API_BASE_URL = f"{urlsplit(API_URL).scheme}://{urlsplit(API_URL).netloc}"
USE_FOLIUM_RENDER = True
USE_MAP_FEATURES_ONLY = True
GENERATE_TABBED_HTML = True
FOLIUM_TILES = "CartoDB positron"
FOLIUM_ZOOM_START = 14
FOLIUM_MARKER_RADIUS = 5
FOLIUM_MARKER_COLOR = "#FF4500"
FOLIUM_MARKER_OPACITY = 0.8
FOLIUM_HEAT_RADIUS = 12
FOLIUM_HEAT_BLUR = 8
FOLIUM_HEAT_MAX_ZOOM = 15
DEFAULT_CENTER = (16.07, 108.21)
TAB_STABLE_TITLE = "Thống kê chi tiết"
TAB_HEATMAP_TITLE = "Heatmap"


def load_payload() -> Dict[str, Any]:
    if INPUT_JSON_PATH:
        return json.loads(INPUT_JSON_PATH.read_text(encoding="utf-8"))
    params = {k: v for k, v in API_PARAMS.items() if v is not None}
    response = requests.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def get_first_value(data: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_point(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    lat = get_first_value(data, ["lat", "latitude", "y", "camera_lat", "real_lat"])
    lon = get_first_value(data, ["lon", "lng", "longitude", "x", "camera_lon", "real_lon"])
    lat_f = to_float(lat)
    lon_f = to_float(lon)
    if lat_f is not None and lon_f is not None:
        return lat_f, lon_f
    geometry = data.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coords = geometry.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            return to_float(coords[1]), to_float(coords[0])
    return None, None


def extract_map_feature_point(det: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    lat = get_first_value(det, [
        "map_feature_lat",
        "map_feature_latitude",
        "feature_lat",
        "object_lat",
        "real_lat",
    ])
    lon = get_first_value(det, [
        "map_feature_lon",
        "map_feature_longitude",
        "feature_lon",
        "object_lon",
        "real_lon",
    ])
    lat_f = to_float(lat)
    lon_f = to_float(lon)
    if lat_f is not None and lon_f is not None:
        return lat_f, lon_f
    for key in ["map_feature", "feature", "object"]:
        value = det.get(key)
        if isinstance(value, dict):
            lat_f, lon_f = extract_point(value)
            if lat_f is not None and lon_f is not None:
                return lat_f, lon_f
    return None, None


def extract_camera_point(det: Dict[str, Any], image: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    for key in ["camera", "camera_position", "image_position"]:
        value = det.get(key)
        if isinstance(value, dict):
            lat_f, lon_f = extract_point(value)
            if lat_f is not None and lon_f is not None:
                return lat_f, lon_f
    return extract_point(image)


def normalize_bbox(bbox: Any) -> Optional[Dict[str, float]]:
    if bbox is None:
        return None
    if isinstance(bbox, dict):
        x = to_float(bbox.get("x") or bbox.get("left"))
        y = to_float(bbox.get("y") or bbox.get("top"))
        w = to_float(bbox.get("w") or bbox.get("width"))
        h = to_float(bbox.get("h") or bbox.get("height"))
        if None not in (x, y, w, h):
            return {"x": x, "y": y, "w": w, "h": h}
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x, y, w, h = (to_float(bbox[0]), to_float(bbox[1]), to_float(bbox[2]), to_float(bbox[3]))
        if None not in (x, y, w, h):
            return {"x": x, "y": y, "w": w, "h": h}
    return None


def normalize_polygons(polygons: Any) -> List[List[List[float]]]:
    if not polygons:
        return []
    if isinstance(polygons, dict):
        normalized = polygons.get("polygons_normalized")
        if normalized:
            return normalize_polygons(normalized)
        polygons_mvt = polygons.get("polygons_mvt")
        extent = to_float(polygons.get("extent"))
        if polygons_mvt and extent:
            return [
                [[point[0] / extent, point[1] / extent] for point in polygon]
                for polygon in polygons_mvt
            ]
    if isinstance(polygons, list):
        if polygons and isinstance(polygons[0], (int, float)):
            return []
        if polygons and isinstance(polygons[0], list):
            if polygons and polygons[0] and isinstance(polygons[0][0], (int, float)):
                return [polygons]
            return polygons
    return []


def normalize_detection(
    det: Dict[str, Any],
    image: Dict[str, Any],
    sequence: Dict[str, Any],
    fallback_id: str,
) -> Optional[Dict[str, Any]]:
    detection_id = get_first_value(det, [
        "detection_id",
        "id",
        "street_light_id",
        "light_id",
        "pkey",
    ]) or fallback_id
    image_id = get_first_value(det, ["image_id", "image_pkey", "image"]) or get_first_value(
        image,
        ["image_id", "image_pkey", "id"],
    )
    sequence_id = get_first_value(det, ["sequence_id", "sequence"]) or get_first_value(
        image,
        ["sequence_id", "sequence"],
    ) or get_first_value(sequence, ["sequence_id", "id"])
    object_label = get_first_value(det, ["object_label", "label", "object_value"]) or "Street light"
    map_feature_id = get_first_value(det, ["map_feature_id", "map_feature", "feature_id", "object_id", "light_id"])
    if isinstance(map_feature_id, dict):
        map_feature_id = get_first_value(map_feature_id, ["map_feature_id", "id", "feature_id"])
    thumb_url = get_first_value(det, ["thumb_url", "thumbnail", "thumb", "thumbnail_url"]) or get_first_value(
        image,
        ["thumb_url", "thumbnail", "thumb", "thumbnail_url", "image_url"],
    )
    captured_at = get_first_value(det, ["detected_at", "captured_at", "captured", "capture_time"]) or get_first_value(
        image,
        ["uploaded_at", "captured_at", "captured", "capture_time"],
    )
    compass_angle = get_first_value(det, ["compass_angle", "bearing", "compass", "heading_angle"]) or get_first_value(
        image,
        ["heading_angle", "compass_angle", "bearing", "compass"],
    )
    mapillary_image_url = get_first_value(det, ["mapillary_image_url", "image_url"]) or get_first_value(
        image,
        ["mapillary_image_url", "image_url"],
    )
    if not mapillary_image_url:
        mapillary_image_url = thumb_url

    thumb_url = resolve_media_url(thumb_url)
    mapillary_image_url = resolve_media_url(mapillary_image_url)

    map_lat, map_lon = extract_map_feature_point(det)
    cam_lat, cam_lon = extract_camera_point(det, image)
    if map_lat is not None and map_lon is not None:
        lat, lon = map_lat, map_lon
        point_source = "map_feature"
    elif cam_lat is not None and cam_lon is not None:
        lat, lon = cam_lat, cam_lon
        point_source = "camera"
    else:
        return None

    bbox = normalize_bbox(det.get("bbox") or det.get("bbox_xywh") or det.get("bounding_box"))
    polygons = normalize_polygons(det.get("polygons") or det.get("segmentation") or det.get("polygon"))

    camera_payload = None
    if cam_lat is not None and cam_lon is not None:
        camera_payload = {"lat": cam_lat, "lon": cam_lon}

    return {
        "lat": lat,
        "lon": lon,
        "point_source": point_source,
        "detection_id": detection_id,
        "image_id": image_id,
        "sequence_id": sequence_id,
        "object_label": object_label,
        "map_feature_id": map_feature_id,
        "camera": camera_payload,
        "bbox": bbox,
        "polygons": polygons,
        "thumb_url": thumb_url,
        "captured_at": captured_at,
        "compass_angle": compass_angle,
        "mapillary_image_url": mapillary_image_url,
    }


def get_image_list(sequence: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ["images", "raw_images", "image_list"]:
        value = sequence.get(key)
        if isinstance(value, list):
            return value
    return []


def get_detection_list(image: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ["street_lights", "detections", "objects", "street_light_detections"]:
        value = image.get(key)
        if isinstance(value, list):
            return value
    return []


def resolve_media_url(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("abfss://"):
            return None
        if value.startswith("/"):
            return f"{API_BASE_URL}{value}"
        return value
    return None


def normalize_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and "detections" in payload and "route" in payload:
        detections = payload.get("detections") or []
        route = payload.get("route") or []
        map_features = payload.get("map_features") or build_map_features(detections)
        sequence_ids = payload.get("sequence_ids") or sorted({
            det.get("sequence_id") for det in detections if det.get("sequence_id")
        })
        stats = build_stats(payload, detections, route, map_features, sequence_ids)
        return {
            "sequence_ids": sequence_ids,
            "stats": stats,
            "detections": detections,
            "map_features": map_features,
            "route": route,
        }

    sequences: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ["sequences", "sequence", "data", "items"]:
            if key in payload:
                sequences = ensure_list(payload[key])
                break
        if not sequences and "images" in payload:
            sequences = [payload]
    elif isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and any(
            key in payload[0] for key in ["images", "raw_images", "image_list"]
        ):
            sequences = payload
        else:
            sequences = []

    detections: List[Dict[str, Any]] = []
    route: List[Dict[str, Any]] = []

    for seq in sequences:
        sequence_id = get_first_value(seq, ["sequence_id", "id"]) or None
        images = get_image_list(seq)
        for image_index, image in enumerate(images):
            image_id = get_first_value(image, ["image_id", "image_pkey", "id"]) or f"img-{image_index}"
            image_lat, image_lon = extract_point(image)
            detections_raw = get_detection_list(image)
            image_detections: List[Dict[str, Any]] = []

            for det_index, det in enumerate(detections_raw):
                normalized = normalize_detection(
                    det,
                    image,
                    seq,
                    f"{image_id}-{det_index}",
                )
                if normalized:
                    detections.append(normalized)
                    image_detections.append(normalized)

            if image_lat is None or image_lon is None:
                continue
            route.append({
                "lat": image_lat,
                "lon": image_lon,
                "image_id": image_id,
                "sequence_id": sequence_id,
                "detection_count": len(image_detections),
                "captured_at": get_first_value(image, ["uploaded_at", "captured_at", "captured", "capture_time"]),
                "compass_angle": get_first_value(image, ["heading_angle", "compass_angle", "bearing", "compass"]),
                "thumb_url": resolve_media_url(get_first_value(
                    image,
                    ["thumbnail_url", "thumb_url", "thumbnail", "thumb", "image_url"],
                )),
                "mapillary_image_url": resolve_media_url(get_first_value(
                    image,
                    ["mapillary_image_url", "image_url", "thumbnail_url"],
                )),
                "detections": image_detections,
            })

    if not sequences and isinstance(payload, list):
        detections = [
            normalize_detection(det, {}, {}, f"det-{index}")
            for index, det in enumerate(payload)
        ]
        detections = [det for det in detections if det]

    if SORT_ROUTE_BY_CAPTURED_AT:
        route.sort(key=lambda item: (item.get("captured_at") or "", item.get("image_id") or ""))

    map_features = build_map_features(detections)
    sequence_ids = sorted({
        det.get("sequence_id") for det in detections if det.get("sequence_id")
    })

    stats = build_stats(payload, detections, route, map_features, sequence_ids)

    return {
        "sequence_ids": sequence_ids,
        "stats": stats,
        "detections": detections,
        "map_features": map_features,
        "route": route,
    }


def build_map_features(detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    features: Dict[str, Dict[str, Any]] = {}
    for item in detections:
        if item.get("point_source") != "map_feature":
            continue
        map_feature_id = item.get("map_feature_id")
        if not map_feature_id:
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        key = str(map_feature_id)
        if key not in features:
            features[key] = {
                "map_feature_id": map_feature_id,
                "lat": lat,
                "lon": lon,
                "detections": [],
                "image_ids": set(),
            }
        features[key]["detections"].append(item)
        image_id = item.get("image_id")
        if image_id:
            features[key]["image_ids"].add(image_id)

    output: List[Dict[str, Any]] = []
    for feature in features.values():
        image_ids = feature.pop("image_ids")
        feature["image_count"] = len(image_ids)
        feature["detection_count"] = len(feature["detections"])
        output.append(feature)
    return output


def build_stats(
    payload: Any,
    detections: List[Dict[str, Any]],
    route: List[Dict[str, Any]],
    map_features: List[Dict[str, Any]],
    sequence_ids: List[str],
) -> Dict[str, Any]:
    stats_payload = payload.get("stats") if isinstance(payload, dict) else {}
    camera_points = sum(1 for item in detections if item.get("point_source") == "camera")
    map_feature_points = sum(1 for item in detections if item.get("point_source") == "map_feature")
    images_with_detections = sum(1 for item in route if item.get("detection_count"))

    stats: Dict[str, Any] = dict(stats_payload or {})
    stats.setdefault("sequences", len(sequence_ids))
    stats.setdefault("images", len(route))
    stats.setdefault("images_with_detections", images_with_detections)
    stats.setdefault("street_light_detections", len(detections))
    stats.setdefault("map_features_scanned", len(map_features))
    stats.setdefault("with_map_feature_position", map_feature_points)
    stats.setdefault("without_street_light_position", camera_points)
    stats.setdefault("with_street_light_position", map_feature_points)
    stats.setdefault("total_records", len(detections))
    stats.setdefault("points_rendered", len(detections))
    stats.setdefault("route_images", len(route))
    stats.setdefault("map_feature_points", map_feature_points)
    stats.setdefault("camera_points", camera_points)
    stats.setdefault("map_feature_objects", len(map_features))
    return stats


def load_template() -> str:
    if TEMPLATE_HTML.exists():
        return TEMPLATE_HTML.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing template: {TEMPLATE_HTML}")


def escape_html(value: Any) -> str:
    text = "" if value is None else str(value)
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def compute_center(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not points:
        return DEFAULT_CENTER
    lat_sum = sum(point[0] for point in points)
    lon_sum = sum(point[1] for point in points)
    count = len(points)
    return lat_sum / count, lon_sum / count


def build_popup_html(item: Dict[str, Any]) -> str:
    lat = item.get("lat")
    lon = item.get("lon")
    lat_text = f"{lat:.6f}" if isinstance(lat, (int, float)) else ""
    lon_text = f"{lon:.6f}" if isinstance(lon, (int, float)) else ""
    mapillary = item.get("mapillary_image_url")
    link = ""
    if mapillary:
        link = f"<br><a href=\"{escape_html(mapillary)}\" target=\"_blank\" rel=\"noreferrer\">Open image</a>"
    return (
        f"<b>Detection:</b> {escape_html(item.get('detection_id'))}<br>"
        f"<b>Image:</b> {escape_html(item.get('image_id'))}<br>"
        f"<b>Sequence:</b> {escape_html(item.get('sequence_id'))}<br>"
        f"<b>Lat:</b> {lat_text}<br>"
        f"<b>Lon:</b> {lon_text}<br>"
        f"<b>Captured:</b> {escape_html(item.get('captured_at'))}"
        f"{link}"
    )


def render_folium_map(data: Dict[str, Any]) -> str:
    try:
        import folium
        from folium.plugins import HeatMap, MarkerCluster
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("folium is required for USE_FOLIUM_RENDER=True") from exc

    detections = data.get("detections") or []
    map_features = data.get("map_features") or []

    if USE_MAP_FEATURES_ONLY and map_features:
        points = [
            (item.get("lat"), item.get("lon"))
            for item in map_features
            if item.get("lat") is not None and item.get("lon") is not None
        ]
        marker_items = [
            {"lat": item.get("lat"), "lon": item.get("lon"), "map_feature_id": item.get("map_feature_id")}
            for item in map_features
            if item.get("lat") is not None and item.get("lon") is not None
        ]
    else:
        points = [
            (item.get("lat"), item.get("lon"))
            for item in detections
            if item.get("lat") is not None and item.get("lon") is not None
        ]
        marker_items = [
            item
            for item in detections
            if item.get("lat") is not None and item.get("lon") is not None
        ]

    center = compute_center(points)
    folium_map = folium.Map(location=center, zoom_start=FOLIUM_ZOOM_START, tiles=FOLIUM_TILES)

    markers_group = folium.FeatureGroup(name="Street lights", show=True)
    marker_cluster = MarkerCluster().add_to(markers_group)
    for item in marker_items:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        popup_html = build_popup_html(item) if "detection_id" in item else (
            f"<b>Map feature:</b> {escape_html(item.get('map_feature_id'))}<br>"
            f"<b>Lat:</b> {lat:.6f}<br>"
            f"<b>Lon:</b> {lon:.6f}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=FOLIUM_MARKER_RADIUS,
            popup=folium.Popup(popup_html, max_width=300),
            color=FOLIUM_MARKER_COLOR,
            fill=True,
            fill_color=FOLIUM_MARKER_COLOR,
            fill_opacity=FOLIUM_MARKER_OPACITY,
            weight=1,
        ).add_to(marker_cluster)
    markers_group.add_to(folium_map)

    heat_points = [
        [item.get("lat"), item.get("lon"), 1 if item.get("point_source") == "map_feature" else 0.6]
        for item in detections
        if item.get("lat") is not None and item.get("lon") is not None
    ]
    if heat_points:
        heat_group = folium.FeatureGroup(name="Heatmap", show=True)
        HeatMap(
            heat_points,
            radius=FOLIUM_HEAT_RADIUS,
            blur=FOLIUM_HEAT_BLUR,
            max_zoom=FOLIUM_HEAT_MAX_ZOOM,
        ).add_to(heat_group)
        heat_group.add_to(folium_map)

    route_items = data.get("route") or []
    if route_items:
        route_group = folium.FeatureGroup(name="Route", show=True)
        route_by_sequence: Dict[str, List[Dict[str, Any]]] = {}
        for index, item in enumerate(route_items):
            key = item.get("sequence_id") or "unknown"
            route_by_sequence.setdefault(key, []).append({**item, "_route_index": index})
        for points_list in route_by_sequence.values():
            points_list.sort(
                key=lambda item: (
                    item.get("captured_at") or "",
                    item.get("image_id") or "",
                    item.get("_route_index") or 0,
                )
            )
            poly_points = [
                (item.get("lat"), item.get("lon"))
                for item in points_list
                if item.get("lat") is not None and item.get("lon") is not None
            ]
            if poly_points:
                folium.PolyLine(poly_points, color="#2563eb", weight=3, opacity=0.7).add_to(route_group)
        route_group.add_to(folium_map)

    if points:
        folium_map.fit_bounds(points)

    folium.LayerControl().add_to(folium_map)
    return folium_map.get_root().render()


def build_tabbed_html(stable_html: str, heatmap_html: str) -> str:
    return f"""<!doctype html>
<html lang=\"vi\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Street Light Views</title>
    <style>
        html, body {{ height: 100%; margin: 0; font-family: Arial, Helvetica, sans-serif; }}
        .app {{ display: flex; flex-direction: column; height: 100%; }}
        .tabs {{ display: flex; gap: 8px; padding: 8px 12px; background: #f8fafc; border-bottom: 1px solid #d6dde6; }}
        .tab {{ border: 1px solid #cbd5e1; background: #ffffff; color: #1f2937; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
        .tab.active {{ background: #2563eb; border-color: #2563eb; color: #ffffff; }}
        .panes {{ flex: 1; position: relative; }}
        .pane {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: none; }}
        .pane.active {{ display: block; }}
    </style>
</head>
<body>
    <div class=\"app\">
        <div class=\"tabs\">
            <button class=\"tab active\" data-tab=\"stable\">{TAB_STABLE_TITLE}</button>
            <button class=\"tab\" data-tab=\"heatmap\">{TAB_HEATMAP_TITLE}</button>
        </div>
        <div class=\"panes\">
                <iframe id=\"pane-stable\" class=\"pane active\" title=\"Stable map\"></iframe>
                <iframe id=\"pane-heatmap\" class=\"pane\" title=\"Heatmap map\"></iframe>
        </div>
    </div>
    <template id=\"stable-html\">{stable_html}</template>
    <template id=\"heatmap-html\">{heatmap_html}</template>
    <script>
        const stableFrame = document.getElementById("pane-stable");
        const heatFrame = document.getElementById("pane-heatmap");
        const stableTemplate = document.getElementById("stable-html");
        const heatTemplate = document.getElementById("heatmap-html");

        function setFrameContent(frame, template) {{
            const blob = new Blob([template.innerHTML], {{ type: "text/html" }});
            frame.src = URL.createObjectURL(blob);
        }}

        setFrameContent(stableFrame, stableTemplate);
        let heatmapLoaded = false;
        function activateTab(tabId) {{
            const tabs = document.querySelectorAll(".tab");
            const panes = document.querySelectorAll(".pane");
            tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabId));
            panes.forEach((pane) => pane.classList.toggle("active", pane.id === `pane-${{tabId}}`));
            if (tabId === "heatmap" && !heatmapLoaded) {{
                    setFrameContent(heatFrame, heatTemplate);
                heatmapLoaded = true;
            }}
        }}

        document.querySelectorAll(".tab").forEach((tab) => {{
            tab.addEventListener("click", () => activateTab(tab.dataset.tab));
        }});
    </script>
</body>
</html>
"""


def inject_data(template: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    replacement = f"const DATA = {payload};"
    if "const DATA =" in template:
        return re.sub(r"const DATA = .*?;", replacement, template, flags=re.S)
    if "</script>" in template:
        return template.replace("</script>", f"{replacement}\n</script>")
    return template + f"\n<script>{replacement}</script>\n"


def main() -> None:
    payload = load_payload()
    data = normalize_payload(payload)
    if GENERATE_TABBED_HTML:
        template = load_template()
        stable_html = inject_data(template, data)
        heatmap_html = render_folium_map(data)
        html = build_tabbed_html(stable_html, heatmap_html)
    elif USE_FOLIUM_RENDER:
        html = render_folium_map(data)
    else:
        template = load_template()
        html = inject_data(template, data)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print("Da tao ban do thanh cong!")
    print(f"Mo file: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()