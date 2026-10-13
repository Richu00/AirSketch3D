"""Validated multi-component contour -> extruded mesh geometry."""
from __future__ import annotations

import numpy as np


def _cross(a, b, c):
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _on_segment(a, b, p, eps=1e-7):
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
        and abs(_cross(a, b, p)) <= eps
    )


def _segments_intersect(a, b, c, d, eps=1e-7):
    ab1, ab2 = _cross(a, b, c), _cross(a, b, d)
    cd1, cd2 = _cross(c, d, a), _cross(c, d, b)
    if ((ab1 > eps > ab2) or (ab2 > eps > ab1)) and ((cd1 > eps > cd2) or (cd2 > eps > cd1)):
        return True
    return _on_segment(a, b, c, eps) or _on_segment(a, b, d, eps) or _on_segment(c, d, a, eps) or _on_segment(c, d, b, eps)


def has_self_intersection(points):
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    if n < 4:
        return False
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segments_intersect(a, b, pts[j], pts[(j + 1) % n]):
                return True
    return False


def polygon_area(points):
    pts = np.asarray(points, dtype=float)
    return 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - pts[:, 1] * np.roll(pts[:, 0], -1)))


def _dedupe(points, min_step):
    pts = np.asarray(points, dtype=np.float32)
    if len(pts) == 0:
        return pts
    keep = [0]
    threshold2 = float(min_step) ** 2
    for i in range(1, len(pts)):
        if float(np.sum((pts[i] - pts[keep[-1]]) ** 2)) >= threshold2:
            keep.append(i)
    return pts[keep]


def resample_closed(points, count=96):
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        return None
    if np.linalg.norm(pts[0] - pts[-1]) < 1e-6:
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    closed = np.vstack([pts, pts[0]])
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    total = float(lengths.sum())
    if total <= 1e-8:
        return None
    distances = np.concatenate([[0.0], np.cumsum(lengths)])
    targets = np.linspace(0.0, total, int(count), endpoint=False)
    return np.column_stack((
        np.interp(targets, distances, closed[:, 0]),
        np.interp(targets, distances, closed[:, 1]),
    ))


def smooth_closed(points, radius=1):
    pts = np.asarray(points, dtype=np.float32)
    if len(pts) < 5 or radius <= 0:
        return pts.copy()
    out = np.empty_like(pts)
    for i in range(len(pts)):
        idx = [(i + j) % len(pts) for j in range(-radius, radius + 1)]
        out[i] = pts[idx].mean(axis=0)
    return out


def _path_length(points, aspect=1.0):
    pts = np.asarray(points, dtype=float)
    if len(pts) < 2:
        return 0.0
    steps = np.diff(pts, axis=0) * np.array([aspect, 1.0])
    return float(np.linalg.norm(steps, axis=1).sum())


def _intersection_point(a, b, c, d):
    r, s = b - a, d - c
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    return a + t * r


def _first_crossing(pts):
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if _segments_intersect(a, b, c, d):
                p = _intersection_point(a, b, c, d)
                if p is None:          # collinear overlap: cannot be repaired
                    return None
                return i, j, p
    return None


def _drop_repeats(pts, eps=1e-9):
    keep = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - keep[-1]) > eps:
            keep.append(p)
    if len(keep) > 1 and np.linalg.norm(keep[0] - keep[-1]) <= eps:
        keep.pop()
    return np.asarray(keep, dtype=float)


def repair_self_intersections(points, max_iter=12):
    """Cut away overshoot tails / small loops, keeping the biggest loop.

    A hand-drawn outline usually crosses itself where the finger overshoots the
    start point.  Instead of rejecting it, split it at the crossing and keep the
    larger of the two loops.  Returns None when it cannot be repaired.
    """
    pts = np.asarray(points, dtype=float)
    for _ in range(max_iter):
        hit = _first_crossing(pts)
        if hit is None:
            return pts
        i, j, p = hit
        loop = np.vstack([p, pts[i + 1:j + 1]])
        outer = np.vstack([pts[:i + 1], p, pts[j + 1:]])
        pts = loop if abs(polygon_area(loop)) >= abs(polygon_area(outer)) else outer
        pts = _drop_repeats(pts)
        if len(pts) < 3:
            return None
    return pts if not has_self_intersection(pts) else None


# ----------------------------------------------------------------- shape snapping
def _dp_open(points, eps):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    length = float(np.linalg.norm(ab))
    if length < 1e-12:
        dist = np.linalg.norm(points - a, axis=1)
    else:
        dist = np.abs(ab[0] * (points[:, 1] - a[1]) - ab[1] * (points[:, 0] - a[0])) / length
    k = int(np.argmax(dist[1:-1])) + 1
    if dist[k] > eps:
        left = _dp_open(points[:k + 1], eps)
        right = _dp_open(points[k:], eps)
        return np.vstack([left[:-1], right])
    return np.vstack([a, b])


def _simplify_closed(points, eps):
    pts = np.asarray(points, dtype=float)
    k = int(np.argmax(np.linalg.norm(pts - pts[0], axis=1)))
    if k == 0:
        return pts
    first = _dp_open(pts[:k + 1], eps)
    second = _dp_open(np.vstack([pts[k:], pts[:1]]), eps)
    return np.vstack([first[:-1], second[:-1]])


def snap_shape(points, aspect=1.0, resample_points=96):
    """Recognise a clean triangle / rectangle / circle in a rough closed outline.

    Deliberately conservative: anything that is not clearly one of those
    (hearts, stars, letters, free-form blobs ...) returns (None, None) and is
    left exactly as drawn.  Works in aspect-corrected space so a circle drawn on
    a 16:9 frame is a circle on screen.
    """
    scale = np.array([aspect, 1.0])
    p = np.asarray(points, dtype=float) * scale
    res = resample_closed(p, 128)
    if res is None:
        return None, None
    perimeter = _path_length(np.vstack([res, res[:1]]))
    if perimeter <= 1e-9:
        return None, None

    simple = _simplify_closed(res, 0.03 * perimeter)
    if len(simple) == 3:
        return simple / scale, "triangle"
    if len(simple) == 4:
        edges = np.roll(simple, -1, axis=0) - simple
        right_angled = True
        for k in range(4):
            e1, e2 = edges[k], edges[(k + 1) % 4]
            denom = max(float(np.linalg.norm(e1) * np.linalg.norm(e2)), 1e-12)
            ang = float(np.degrees(np.arccos(np.clip(np.dot(e1, e2) / denom, -1.0, 1.0))))
            if abs(ang - 90.0) > 22.0:
                right_angled = False
        if not right_angled:
            return simple / scale, "quad"
        u = edges[0] - edges[2]
        u = u / max(float(np.linalg.norm(u)), 1e-12)
        tilt = float(np.degrees(np.arctan2(u[1], u[0]))) % 90.0
        if min(tilt, 90.0 - tilt) <= 12.0:
            u = np.array([1.0, 0.0])
        w = np.array([-u[1], u[0]])
        pu, pw = simple @ u, simple @ w
        u0, u1, w0, w1 = pu.min(), pu.max(), pw.min(), pw.max()
        rect = np.array([u * a + w * b for a, b in ((u0, w0), (u1, w0), (u1, w1), (u0, w1))])
        return rect / scale, "rectangle"

    centre = res.mean(axis=0)
    radii = np.linalg.norm(res - centre, axis=1)
    mean_r = float(radii.mean())
    if mean_r > 1e-9 and float(radii.std()) / mean_r < 0.07:
        t = np.linspace(0.0, 2.0 * np.pi, int(resample_points), endpoint=False)
        circle = centre + mean_r * np.column_stack([np.cos(t), np.sin(t)])
        return circle / scale, "circle"
    return None, None


def _clean_stroke(stroke, min_points, close_snap_distance, min_component_area, aspect,
                  auto_close_ratio=0.0, repair_crossings=False, notes=None):
    pts = _dedupe(stroke, min_step=0.0015)
    if len(pts) < min_points:
        return None, "too_short"

    gap = float(np.linalg.norm((pts[0] - pts[-1]) * np.array([aspect, 1.0])))
    if gap > close_snap_distance:
        length = _path_length(pts, aspect)
        if auto_close_ratio and length > 0 and gap <= auto_close_ratio * length:
            # A "C"-shaped outline: the closing edge is implicit in the polygon, so
            # simply accept it instead of making the user trace back to the start.
            if notes is not None:
                notes.append("auto-closed a gap")
        else:
            return None, f"open:{gap:.3f}/{close_snap_distance:.3f}"
    # Do not retain a duplicated first/last point during intersection tests;
    # the closing edge is implicit in the polygon representation.
    if np.linalg.norm(pts[0] - pts[-1]) < 1e-6:
        pts = pts[:-1]

    if has_self_intersection(pts):
        fixed = repair_self_intersections(pts) if repair_crossings else None
        if fixed is None:
            return None, "self_intersection"
        if notes is not None:
            notes.append("trimmed an overlapping tail")
        pts = fixed

    area = abs(polygon_area(pts))
    if area < min_component_area:
        return None, "degenerate"

    return pts, "ok"


def build_3d_shape_ex(strokes, resample_points=96, aspect=1.0, min_points=15,
                      close_snap_distance=0.035, min_component_area=0.0015,
                      auto_close_ratio=0.0, repair_crossings=False, snap_shapes=False,
                      strict_indices=()):
    """Like build_3d_shape but also returns human-readable notes (what was fixed up)."""
    components = []
    problems = []
    notes = []
    for index, stroke in enumerate(strokes):
        if len(stroke) < min_points:
            continue
        strict = index in strict_indices          # e.g. an arc left behind by the eraser
        cleaned, status = _clean_stroke(
            stroke, min_points, close_snap_distance, min_component_area, aspect,
            auto_close_ratio=0.0 if strict else auto_close_ratio,
            repair_crossings=repair_crossings and not strict, notes=notes,
        )
        if status != "ok":
            problems.append((index, status))
            continue
        if snap_shapes:
            snapped, kind = snap_shape(cleaned, aspect, resample_points)
            if snapped is not None:
                notes.append(f"snapped to {kind}")
                components.append(np.asarray(snapped, dtype=np.float32))
                continue
        outline = resample_closed(cleaned, resample_points)
        if outline is None:
            problems.append((index, "resample_failed"))
            continue
        components.append(smooth_closed(outline))

    if not components:
        return None, problems or [(0, "no_valid_closed_stroke")], notes
    # Erasing can legitimately leave short/open fragments behind. They are not
    # model components and should not invalidate an otherwise valid closed shape.
    # Only fail when there is no valid component at all.

    # Convert image-space y-down to model-space y-up once, then normalize all
    # components against the same bounding box so disconnected shapes preserve
    # their relative placement.
    model_components = []
    all_points = []
    for component in components:
        c = component.astype(np.float32).copy()
        c[:, 0] *= float(aspect)
        c[:, 1] *= -1.0
        model_components.append(c)
        all_points.append(c)

    combined = np.vstack(all_points)
    minimum = combined.min(axis=0)
    maximum = combined.max(axis=0)
    center = (minimum + maximum) * 0.5
    span = max(float((maximum - minimum).max()), 1e-6)
    normalized = [((component - center) / span).astype(np.float32) for component in model_components]
    return normalized, [], notes


def build_3d_shape(strokes, resample_points=96, aspect=1.0, min_points=15,
                   close_snap_distance=0.035, min_component_area=0.0015, **options):
    """Validate each stroke independently and return normalized closed outlines.

    Strict by default (open / self-crossing strokes are reported as problems).
    Pass auto_close_ratio / repair_crossings / snap_shapes for the forgiving mode
    the live engine uses.
    """
    outlines, problems, _ = build_3d_shape_ex(
        strokes, resample_points=resample_points, aspect=aspect, min_points=min_points,
        close_snap_distance=close_snap_distance, min_component_area=min_component_area, **options,
    )
    return outlines, problems


def _point_in_triangle(p, a, b, c):
    c1, c2, c3 = _cross(a, b, p), _cross(b, c, p), _cross(c, a, p)
    return not ((c1 < -1e-8 or c2 < -1e-8 or c3 < -1e-8) and (c1 > 1e-8 or c2 > 1e-8 or c3 > 1e-8))


def triangulate(polygon):
    pts = np.asarray(polygon, dtype=float)
    if len(pts) < 3:
        return []
    indices = list(range(len(pts)))
    if polygon_area(pts) < 0:
        indices.reverse()
    triangles = []
    guard = 0
    while len(indices) > 3 and guard < len(pts) * len(pts):
        guard += 1
        found = False
        m = len(indices)
        for k in range(m):
            ia, ib, ic = indices[(k - 1) % m], indices[k], indices[(k + 1) % m]
            a, b, c = pts[ia], pts[ib], pts[ic]
            if _cross(a, b, c) <= 1e-8:
                continue
            if any(j not in (ia, ib, ic) and _point_in_triangle(pts[j], a, b, c) for j in indices):
                continue
            triangles.append((ia, ib, ic))
            del indices[k]
            found = True
            break
        if not found:
            return []
    if len(indices) == 3:
        triangles.append(tuple(indices))
    return triangles


def build_mesh(outlines, height=0.6):
    """Triangulate and extrude all normalized outlines for optional backend export."""
    vertices, faces = [], []
    for outline in outlines:
        polygon = np.asarray(outline, dtype=np.float32)
        triangles = triangulate(polygon)
        if not triangles:
            continue
        base = len(vertices)
        n = len(polygon)
        vertices.extend([(float(x), float(y), 0.0) for x, y in polygon])
        vertices.extend([(float(x), float(y), float(height)) for x, y in polygon])
        for a, b, c in triangles:
            faces.append((base + a, base + c, base + b))
            faces.append((base + n + a, base + n + b, base + n + c))
        for i in range(n):
            j = (i + 1) % n
            faces.append((base + i, base + j, base + n + j))
            faces.append((base + i, base + n + j, base + n + i))
    if not vertices:
        raise ValueError("No triangulatable outline was found.")
    return np.asarray(vertices, dtype=np.float32), faces
