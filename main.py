import math
import os
from functools import partial
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.stencilview import StencilView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.graphics import (
    Color, Line, Rectangle, Ellipse, RoundedRectangle, Quad,
    PushMatrix, PopMatrix, Rotate,
)
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp, sp
from kivy.clock import Clock
from kivy.utils import platform

# Android Runtime Permission Request
if platform == 'android':
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE
        ])
    except Exception as e:
        print("Android permission error:", e)

# PDF Generation Imports
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

# ---------- Theme ----------
C_BG = (0.92, 0.95, 0.99, 1)
C_PRIMARY = (0.04, 0.38, 0.55, 1)
C_GREEN = (0.10, 0.60, 0.40, 1)
C_ORANGE = (0.96, 0.50, 0.10, 1)
C_PURPLE = (0.52, 0.28, 0.78, 1)
C_RED = (0.86, 0.24, 0.28, 1)
C_BLUE = (0.16, 0.45, 0.85, 1)
C_TEAL = (0.05, 0.62, 0.65, 1)
C_TEXT = (0.12, 0.17, 0.25, 1)

# প্রতিটি প্লটের জন্য আলাদা হালকা রঙ (ডায়াগ্রাম ও PDF)
PLOT_COLORS = [
    (0.78, 0.93, 0.84), (1.00, 0.89, 0.74), (0.80, 0.86, 0.98),
    (0.98, 0.82, 0.88), (0.93, 0.93, 0.74), (0.80, 0.94, 0.95),
]

Window.clearcolor = C_BG
SQFT_PER_SHATAK = 435.6
MAX_PLOTS = 40  # একবারে সর্বোচ্চ প্লট সংখ্যা (হ্যাং এড়াতে)

# বাহুর দিক-ভিত্তিক নাম (ডায়াগ্রামে P1-P2 ওপরে = উত্তর)
SIDE_NAME = {1: "North 1", 2: "East 2", 3: "South 3", 4: "West 4"}


# ==========================================
# 1. Math & Geometry Validation Engine (Circle-Circle Intersection)
# ==========================================
def circle_intersection(c1, r1, c2, r2):
    """দুটি বৃত্তের ছেদবিন্দু (Circle-Circle Intersection) বের করার নির্ভুল ভেক্টর জ্যামিতি পদ্ধতি"""
    x1, y1 = c1
    x2, y2 = c2
    d = math.hypot(x2 - x1, y2 - y1)
    if d > r1 + r2 or d < abs(r1 - r2) or d == 0:
        raise ValueError(f"Geometry error: Circles do not intersect (d={d:.2f}, r1={r1}, r2={r2})")
    a = (r1**2 - r2**2 + d**2) / (2 * d)
    h_sq = r1**2 - a**2
    h = math.sqrt(max(0.0, h_sq))
    x2_mid = x1 + a * (x2 - x1) / d
    y2_mid = y1 + a * (y2 - y1) / d
    rx = -(y2 - y1) * (h / d)
    ry = (x2 - x1) * (h / d)
    return (x2_mid + rx, y2_mid + ry), (x2_mid - rx, y2_mid - ry)


def get_diagonal_bounds(s1, s2, s3, s4, diag_type="Pt 1-3"):
    s1, s2, s3, s4 = float(s1), float(s2), float(s3), float(s4)
    if diag_type == "Pt 1-3":
        min_d = max(abs(s1 - s2), abs(s3 - s4))
        max_d = min(s1 + s2, s3 + s4)
    else:  # "Pt 2-4"
        min_d = max(abs(s1 - s4), abs(s2 - s3))
        max_d = min(s1 + s4, s2 + s3)
    return min_d, max_d


def calculate_quadrilateral(s1, s2, s3, s4, diag_val, diag_type="Pt 1-3"):
    d_val = float(diag_val)
    s1, s2, s3, s4 = float(s1), float(s2), float(s3), float(s4)

    min_allowed, max_allowed = get_diagonal_bounds(s1, s2, s3, s4, diag_type)

    if not (min_allowed <= d_val <= max_allowed):
        raise ValueError(
            f"Input diagonal is geometrically impossible!\n"
            f"The {diag_type} diagonal value must be between "
            f"{min_allowed:.2f} ft and {max_allowed:.2f} ft based on the sides."
        )

    if diag_type == "Pt 1-3":
        p1 = (0.0, 0.0)
        p2 = (s1, 0.0)
        
        pt3_a, pt3_b = circle_intersection(p1, d_val, p2, s2)
        p3 = pt3_a if pt3_a[1] < pt3_b[1] else pt3_b

        pt4_a, pt4_b = circle_intersection(p1, s4, p3, s3)
        
        best_p4 = None
        max_a = -1
        for cand in [pt4_a, pt4_b]:
            pts = [p1, p2, p3, cand]
            area = polygon_area(pts)
            if area > max_a:
                max_a = area
                best_p4 = cand
        p4 = best_p4

        return [p1, p2, p3, p4]

    else:  # "Pt 2-4"
        p1 = (0.0, 0.0)
        p2 = (s1, 0.0)
        
        pt4_a, pt4_b = circle_intersection(p1, s4, p2, d_val)
        p4 = pt4_a if pt4_a[1] < pt4_b[1] else pt4_b

        pt3_a, pt3_b = circle_intersection(p2, s2, p4, s3)
        
        best_p3 = None
        max_a = -1
        for cand in [pt3_a, pt3_b]:
            pts = [p1, p2, cand, p4]
            area = polygon_area(pts)
            if area > max_a:
                max_a = area
                best_p3 = cand
        p3 = best_p3

        return [p1, p2, p3, p4]


def polygon_area(pts):
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def line_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0 <= t <= 1 and 0 <= u <= 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def dist(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def divide_polygon_directional(pts, num_parts, target_area_sqft, direction, max_cuts=0):
    total_area = polygon_area(pts)

    if target_area_sqft >= total_area and target_area_sqft > 0:
        return [], 0, "Specified plot area cannot be equal to or greater than total area!", [], []

    is_vertical = direction in ["West to East", "East to West"]
    reverse_order = direction in ["East to West", "North to South"]

    idx = 0 if is_vertical else 1
    vals = [p[idx] for p in pts]
    min_v, max_v = min(vals), max(vals)

    def area_upto(V):
        poly = list(pts)
        clipped = []
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            p1_in = p1[idx] <= V
            p2_in = p2[idx] <= V

            if p1_in and p2_in:
                clipped.append(p2)
            elif p1_in and not p2_in:
                t = (V - p1[idx]) / (p2[idx] - p1[idx]) if p2[idx] != p1[idx] else 0
                clipped.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])))
            elif not p1_in and p2_in:
                t = (V - p1[idx]) / (p2[idx] - p1[idx]) if p2[idx] != p1[idx] else 0
                clipped.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])))
                clipped.append(p2)
        return polygon_area(clipped) if len(clipped) >= 3 else 0.0

    div_lines = []
    targets_to_find = []

    if target_area_sqft > 0:
        part_area = target_area_sqft
        # একই ক্ষেত্রফলের প্লট বারবার কাটা হয়, যতক্ষণ জমি থাকে (শেষে অবশিষ্ট প্লট)
        k = 1
        while k * part_area < total_area - 0.5 and k < MAX_PLOTS and (not max_cuts or k <= max_cuts):
            cum = k * part_area
            targets_to_find.append((total_area - cum) if reverse_order else cum)
            k += 1
    else:
        part_area = total_area / max(1, num_parts)
        for k in range(1, num_parts):
            target = (total_area - (k * part_area)) if reverse_order else (k * part_area)
            targets_to_find.append(target)

    for target in targets_to_find:
        if target <= 0 or target >= total_area:
            continue
        low, high = min_v, max_v
        for _ in range(80):
            mid = (low + high) / 2.0
            if area_upto(mid) < target:
                low = mid
            else:
                high = mid
        div_lines.append((low + high) / 2.0)

    partition_segments = []
    sub_edge_segments = []

    span_x = max(p[0] for p in pts) - min(p[0] for p in pts)
    span_y = max(p[1] for p in pts) - min(p[1] for p in pts)
    pad = max(span_x, span_y) * 3.0

    min_x, max_x = min(p[0] for p in pts) - pad, max(p[0] for p in pts) + pad
    min_y, max_y = min(p[1] for p in pts) - pad, max(p[1] for p in pts) + pad

    n = len(pts)

    for div_v in div_lines:
        p_a, p_b = ((div_v, min_y), (div_v, max_y)) if is_vertical else ((min_x, div_v), (max_x, div_v))
        intersections = []
        for i in range(n):
            pt_int = line_intersection(p_a, p_b, pts[i], pts[(i + 1) % n])
            if pt_int:
                intersections.append((pt_int, i))

        if len(intersections) >= 2:
            intersections.sort(key=lambda item: item[0][1] if is_vertical else item[0][0])
            p_start, p_end = intersections[0][0], intersections[1][0]
            partition_segments.append((p_start, p_end))

    if is_vertical:
        bottom_pts = [pts[0]]
        top_pts = [pts[3]]

        for div_v in div_lines:
            p_a, p_b = (div_v, min_y), (div_v, max_y)

            int_bot = line_intersection(p_a, p_b, pts[0], pts[1])
            if int_bot:
                bottom_pts.append(int_bot)

            int_top = line_intersection(p_a, p_b, pts[3], pts[2])
            if int_top:
                top_pts.append(int_top)

        bottom_pts.append(pts[1])
        top_pts.append(pts[2])

        bottom_pts.sort(key=lambda p: dist(pts[0], p))
        for i in range(len(bottom_pts) - 1):
            if dist(bottom_pts[i], bottom_pts[i + 1]) > 0.01:
                sub_edge_segments.append((bottom_pts[i], bottom_pts[i + 1], "bottom"))

        top_pts.sort(key=lambda p: dist(pts[3], p))
        for i in range(len(top_pts) - 1):
            if dist(top_pts[i], top_pts[i + 1]) > 0.01:
                sub_edge_segments.append((top_pts[i], top_pts[i + 1], "top"))

    else:
        left_pts = [pts[3]]
        right_pts = [pts[2]]

        for div_v in div_lines:
            p_a, p_b = (min_x, div_v), (max_x, div_v)

            int_left = line_intersection(p_a, p_b, pts[3], pts[0])
            if int_left:
                left_pts.append(int_left)

            int_right = line_intersection(p_a, p_b, pts[2], pts[1])
            if int_right:
                right_pts.append(int_right)

        left_pts.append(pts[0])
        right_pts.append(pts[1])

        left_pts.sort(key=lambda p: dist(pts[3], p))
        for i in range(len(left_pts) - 1):
            if dist(left_pts[i], left_pts[i + 1]) > 0.01:
                sub_edge_segments.append((left_pts[i], left_pts[i + 1], "left"))

        right_pts.sort(key=lambda p: dist(pts[2], p))
        for i in range(len(right_pts) - 1):
            if dist(right_pts[i], right_pts[i + 1]) > 0.01:
                sub_edge_segments.append((right_pts[i], right_pts[i + 1], "right"))

    return div_lines, part_area, is_vertical, partition_segments, sub_edge_segments


# ==========================================
# 1b. Adjustable Cut Engine (fixed area, adjustable adjacent sides)
# ==========================================
class AdjustableCut:
    """
    বন্টনকৃত প্লটের শুরুর বাহু (Start Side) সংলগ্ন দুই বাহুর (A ও B) কাটা অংশের দৈর্ঘ্য
    কম-বেশি করলেও প্লটের ক্ষেত্রফল (target) একই থাকে।
    A বা B এর একটির মান দিলে অপরটি স্বয়ংক্রিয়ভাবে হিসাব হয়।
    প্লট = [a0, Qa, Qb, b0]  (Qa: A বাহুর উপর a0 থেকে x দূরত্বে, Qb: B বাহুর উপর b0 থেকে y দূরত্বে)
    """
    EPS = 1e-6

    def __init__(self, pts, direction, target_area):
        self.pts = pts
        self.direction = direction
        self.target = float(target_area)
        self.is_vertical = direction in ("West to East", "East to West")

        if self.is_vertical:
            # কাটা হয় Side 1 (P1-P2) ও Side 3 (P4-P3) এর উপর
            cands = [
                ((0, 1, 3, 2), (pts[0][0] + pts[3][0]) / 2.0),  # শুরুর বাহু P1-P4 (পশ্চিম দিক)
                ((1, 0, 2, 3), (pts[1][0] + pts[2][0]) / 2.0),  # শুরুর বাহু P2-P3 (পূর্ব দিক)
            ]
            pick_low = (direction == "West to East")
            self.pos_a, self.pos_b = "bottom", "top"
            self.side_a_no, self.side_b_no = 1, 3
        else:
            # কাটা হয় Side 4 (P4-P1) ও Side 2 (P3-P2) এর উপর
            cands = [
                ((0, 3, 1, 2), (pts[0][1] + pts[1][1]) / 2.0),  # শুরুর বাহু P1-P2
                ((3, 0, 2, 1), (pts[3][1] + pts[2][1]) / 2.0),  # শুরুর বাহু P4-P3
            ]
            pick_low = (direction == "South to North")
            self.pos_a, self.pos_b = "left", "right"
            self.side_a_no, self.side_b_no = 4, 2

        chooser = min if pick_low else max
        idxs = chooser(cands, key=lambda c: c[1])[0]
        self.ia0, self.ia1, self.ib0, self.ib1 = idxs
        self.a0, self.a1 = pts[self.ia0], pts[self.ia1]
        self.b0, self.b1 = pts[self.ib0], pts[self.ib1]
        self.La = dist(self.a0, self.a1)
        self.Lb = dist(self.b0, self.b1)

        self.range_a = self._calc_range("a")
        self.range_b = self._calc_range("b")
        self.ok = (
            self.target > 0
            and self.range_a[0] <= self.range_a[1] + 1e-9
            and self.range_b[0] <= self.range_b[1] + 1e-9
        )

    # ---- basic geometry ----
    @staticmethod
    def _lerp(p0, p1, t):
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    def point_a(self, x):
        return self._lerp(self.a0, self.a1, x / self.La if self.La > 0 else 0.0)

    def point_b(self, y):
        return self._lerp(self.b0, self.b1, y / self.Lb if self.Lb > 0 else 0.0)

    def poly(self, x, y):
        return [self.a0, self.point_a(x), self.point_b(y), self.b0]

    def area(self, x, y):
        return polygon_area(self.poly(x, y))

    def _area_of(self, which, v, other):
        return self.area(v, other) if which == "a" else self.area(other, v)

    @staticmethod
    def _bisect(fn, target, lo, hi):
        for _ in range(90):
            mid = (lo + hi) / 2.0
            if fn(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    # ---- feasible range & solving ----
    def _calc_range(self, which):
        T = self.target
        L = self.La if which == "a" else self.Lb
        L_other = self.Lb if which == "a" else self.La

        # সর্বনিম্ন মান: অপর বাহু সর্বোচ্চ ধরলেও ক্ষেত্রফল T এর কম হলে চলবে না
        if self._area_of(which, 0.0, L_other) >= T - self.EPS:
            lo = 0.0
        else:
            lo = self._bisect(lambda v: self._area_of(which, v, L_other), T, 0.0, L)

        # সর্বোচ্চ মান: অপর বাহু ০ ধরলেও ক্ষেত্রফল T এর বেশি হলে চলবে না
        if self._area_of(which, L, 0.0) <= T + self.EPS:
            hi = L
        else:
            hi = self._bisect(lambda v: self._area_of(which, v, 0.0), T, 0.0, L)
        return lo, hi

    def solve(self, which, v):
        """which = 'a' বা 'b' এর মান v দিলে অপর বাহুর মান বের করে (ক্ষেত্রফল ঠিক রেখে)।"""
        T = self.target
        L_other = self.Lb if which == "a" else self.La
        if self._area_of(which, v, 0.0) > T + self.EPS:
            return None
        if self._area_of(which, v, L_other) < T - self.EPS:
            return None
        return self._bisect(lambda o: self._area_of(which, v, o), T, 0.0, L_other)

    def default_from_line(self, line_v):
        """সরল (straight) বন্টন রেখা থেকে A ও B এর প্রাথমিক মান।"""
        idx = 0 if self.is_vertical else 1
        d = self.a1[idx] - self.a0[idx]
        t = 0.0 if abs(d) < 1e-9 else (line_v - self.a0[idx]) / d
        x = min(1.0, max(0.0, t)) * self.La
        lo, hi = self.range_a
        x = min(hi, max(lo, x))
        y = self.solve("a", x)
        return x, y

    def default_parallel(self):
        """শুরুর বাহু (a0-b0) এর সমান্তরাল রেখা দিয়ে কাটলে A ও B এর প্রাথমিক মান।
        শুরুর বাহু থেকে লম্ব-দূরত্ব h এর রেখা A ও B কে x = h/na, y = h/nb দূরত্বে কাটে;
        h এমনভাবে বের করা হয় যাতে ক্ষেত্রফল ঠিক target হয়। সম্ভব না হলে None।"""
        dx, dy = self.b0[0] - self.a0[0], self.b0[1] - self.a0[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-9 or self.La < 1e-9 or self.Lb < 1e-9:
            return None
        nx, ny = -dy / ln, dx / ln
        ax, ay = self.a1[0] - self.a0[0], self.a1[1] - self.a0[1]
        if nx * ax + ny * ay < 0:
            nx, ny = -nx, -ny
        na = (nx * ax + ny * ay) / self.La
        nb = (nx * (self.b1[0] - self.b0[0]) + ny * (self.b1[1] - self.b0[1])) / self.Lb
        if na < 1e-6 or nb < 1e-6:
            return None
        h_max = min(self.La * na, self.Lb * nb)
        if self.area(h_max / na, h_max / nb) >= self.target - self.EPS:
            # সমান্তরাল রেখা এখনও A ও B দুই বাহুর ভেতরেই থাকে
            h = self._bisect(lambda hh: self.area(hh / na, hh / nb), self.target, 0.0, h_max)
            return h / na, h / nb
        # সমান্তরাল রেখা একটি বাহুর শেষ কোণে পৌঁছে গেছে: ঐ কোণকে কেন্দ্র করে রেখা ঘোরে (fan),
        # ফলে রেখাগুলো কখনো একে অপরকে কাটে না।
        if self.Lb * nb <= self.La * na:
            x = self.solve("b", self.Lb)
            return (x, self.Lb) if x is not None else None
        y = self.solve("a", self.La)
        return (self.La, y) if y is not None else None

    # ---- result for drawing / report ----
    def geometry(self, x, y):
        qa, qb = self.point_a(x), self.point_b(y)
        sub_edges = []
        for p0, pq, p1, pos in ((self.a0, qa, self.a1, self.pos_a), (self.b0, qb, self.b1, self.pos_b)):
            if dist(p0, pq) > 0.01:
                sub_edges.append((p0, pq, pos))
            if dist(pq, p1) > 0.01:
                sub_edges.append((pq, p1, pos))
        return {
            "qa": qa, "qb": qb,
            "partition_segments": [(qa, qb)],
            "sub_edge_segments": sub_edges,
            "cut_len": dist(qa, qb),
            "start_len": dist(self.a0, self.b0),
            "area": self.area(x, y),
        }



class MultiCutAdjuster:
    """
    একাধিক বন্টন রেখা (cut) একসাথে পরিচালনা করে।
    প্রতিটি cut-এর ক্ষেত্রফল (শুরুর বাহু থেকে ক্রমযোগ) ঠিক থাকে, তাই
    একটি cut কম-বেশি করলেও সব প্লটের ক্ষেত্রফল অপরিবর্তিত থাকে।
    পাশের cut এর সাথে যেন ক্রস না করে, সেজন্য রেঞ্জ প্রতিবেশী cut দিয়ে সীমাবদ্ধ।
    """

    def __init__(self, pts, direction, targets):
        self.pts = pts
        self.direction = direction
        self.total_area = polygon_area(pts)
        self.cuts = [AdjustableCut(pts, direction, t) for t in targets]
        self.n = len(self.cuts)
        c0 = self.cuts[0]
        self.c0 = c0
        self.is_vertical = c0.is_vertical
        self.La, self.Lb = c0.La, c0.Lb
        self.ok = self.n > 0 and all(c.ok for c in self.cuts)
        self.xy = []
        self.parallel = False

    def init_from_lines(self, div_lines, parallel=False):
        self.xy = []
        self.parallel = parallel
        if len(div_lines) != self.n:
            return False
        for c, v in zip(self.cuts, div_lines):
            res = c.default_parallel() if parallel else None
            if res is None:
                res = c.default_from_line(v)
            x, y = res
            if y is None:
                return False
            self.xy.append([x, y])
        return True

    def neighbors(self, k):
        lo = tuple(self.xy[k - 1]) if k > 0 else (0.0, 0.0)
        hi = tuple(self.xy[k + 1]) if k < self.n - 1 else (self.La, self.Lb)
        return lo, hi

    def bounds(self, k, which):
        c = self.cuts[k]
        (xl, yl), (xu, yu) = self.neighbors(k)
        ra, rb = c.range_a, c.range_b

        def clamp(v, r):
            return min(r[1], max(r[0], v))

        if which == "a":
            lo, hi = max(ra[0], xl), min(ra[1], xu)
            t = c.solve("b", clamp(yu, rb))
            if t is not None:
                lo = max(lo, t)
            t = c.solve("b", clamp(yl, rb))
            if t is not None:
                hi = min(hi, t)
        else:
            lo, hi = max(rb[0], yl), min(rb[1], yu)
            t = c.solve("a", clamp(xu, ra))
            if t is not None:
                lo = max(lo, t)
            t = c.solve("a", clamp(xl, ra))
            if t is not None:
                hi = min(hi, t)
        if lo > hi:
            lo = hi = (lo + hi) / 2.0
        return lo, hi

    def plot_areas_now(self):
        T = [c.target for c in self.cuts]
        edges = [0.0] + T + [self.total_area]
        return [edges[i + 1] - edges[i] for i in range(self.n + 1)]

    def set_plot_area(self, i, new_area, min_area=1.0):
        """i নম্বর প্লটের ক্ষেত্রফল new_area করে।
        - শেষ প্লটের আগের যেকোনো প্লট বদলালে তার পরের সব রেখা সমান পরিমাণ সরে যায়; তাই
          মাঝের প্লটগুলোর ক্ষেত্রফল ঠিক থাকে এবং কম-বেশি হয় শেষের অবশিষ্ট জমি (Remaining) থেকে।
        - শেষ প্লট বদলালে তার আগের প্লট (Plot n) বাকি পরিবর্তন শুষে নেয়।
        ফেরত: (ok, message)"""
        n = self.n
        areas = self.plot_areas_now()
        T = [c.target for c in self.cuts]
        if i < n:
            shift = list(range(i, n))
            delta = new_area - areas[i]
            a_hi = areas[i] + areas[n] - min_area
        else:
            shift = [n - 1]
            delta = (self.total_area - new_area) - T[n - 1]
            a_hi = areas[n] + areas[n - 1] - min_area
        newT = list(T)
        for j in shift:
            newT[j] = T[j] + delta
        edges = [0.0] + newT + [self.total_area]
        if new_area < min_area - 1e-6 or any(edges[m + 1] - edges[m] < min_area - 1e-6 for m in range(n + 1)):
            who = "remaining land" if i < n else f"Plot {n}"
            return False, (f"Plot {i + 1} area must be between {min_area:.2f} and {a_hi:.2f} sq.ft "
                           f"({min_area / SQFT_PER_SHATAK:.2f} to {a_hi / SQFT_PER_SHATAK:.2f} Shatak), "
                           f"because the {who} must stay at least {min_area:.0f} sq.ft.")

        saved = {j: (self.cuts[j].target, self.cuts[j].range_a, self.cuts[j].range_b, list(self.xy[j]))
                 for j in shift}

        def restore():
            for j, (t, ra, rb, xy) in saved.items():
                self.cuts[j].target, self.cuts[j].range_a, self.cuts[j].range_b = t, ra, rb
                self.xy[j] = xy

        order = sorted(shift, reverse=(delta > 0))   # বাড়লে শেষ রেখা আগে সরাই, কমলে প্রথমটা আগে
        for j in order:
            c = self.cuts[j]
            c.target = newT[j]
            c.range_a = c._calc_range("a")
            c.range_b = c._calc_range("b")
            lines = divide_polygon_directional(self.pts, 1, newT[j], self.direction)[0]
            if not lines:
                restore()
                return False, "This area is not possible."
            res = c.default_parallel() if getattr(self, "parallel", False) else None
            x, y = res if res is not None else c.default_from_line(lines[0])
            if y is None:
                restore()
                return False, "This area is not possible for this plot shape."
            self.xy[j] = [x, y]
            lo, hi = self.bounds(j, "a")
            x2 = min(hi, max(lo, x))
            if abs(x2 - x) > 1e-9:
                y2 = c.solve("a", x2)
                if y2 is None:
                    restore()
                    return False, "This area is not possible without overlapping the neighbouring plot."
                self.xy[j] = [x2, y2]
        return True, ""

    def geometry(self):
        c0 = self.c0
        qas = [c.point_a(x) for c, (x, y) in zip(self.cuts, self.xy)]
        qbs = [c.point_b(y) for c, (x, y) in zip(self.cuts, self.xy)]
        part_segs = list(zip(qas, qbs))

        sub = []
        for mids, p0, p1, pos in ((qas, c0.a0, c0.a1, c0.pos_a), (qbs, c0.b0, c0.b1, c0.pos_b)):
            chain = [p0] + mids + [p1]
            for u, v in zip(chain, chain[1:]):
                if dist(u, v) > 0.01:
                    sub.append((u, v, pos))

        ca = [c0.a0] + qas + [c0.a1]
        cb = [c0.b0] + qbs + [c0.b1]
        polys = [[ca[i], ca[i + 1], cb[i + 1], cb[i]] for i in range(self.n + 1)]
        plot_areas = [polygon_area(p) for p in polys]

        return {
            "partition_segments": part_segs,
            "sub_edge_segments": sub,
            "plot_polys": polys,
            "plot_areas": plot_areas,
            "cut_lens": [dist(p, q) for p, q in part_segs],
            "start_len": dist(c0.a0, c0.b0),
        }


# ==========================================
# 1c. Label Layout Engine (ডায়াগ্রাম ও PDF দুটোতেই একই নিয়মে লেবেল বসায়)
# ==========================================
LABEL_BASE_SIZE = {"side": 10.5, "sub": 9.0, "cut": 9.0, "pt": 10.0, "diag": 9.5,
                   "tagno": 10.0, "tagarea": 10.0}
LABEL_COLORS = {
    "side": (0.78, 0.10, 0.15, 1),   # মূল বাহু - গাঢ় লাল (বাইরে)
    "sub": (0.05, 0.33, 0.80, 1),    # বন্টনকৃত অংশ - নীল (ভেতরে)
    "cut": (0.50, 0.10, 0.65, 1),    # বন্টন রেখা - বেগুনি
    "pt": (0.0, 0.35, 0.25, 1),      # P1..P4
    "diag": (0.85, 0.20, 0.05, 1),   # প্লটের কর্ণ - কমলা-লাল
    "tagno": (0.10, 0.12, 0.55, 1),  # প্লট নম্বর - গাঢ় নীল
    "tagarea": (0.0, 0.38, 0.12, 1), # প্লটের শতক - গাঢ় সবুজ
}


def label_angle(dx, dy):
    """বাহুর দিক অনুযায়ী লেখা হরাইজন্টাল / ভার্টিকাল / ঢালু - স্বয়ংক্রিয়ভাবে ঠিক করে।"""
    a = math.degrees(math.atan2(dy, dx))
    if a > 90:
        a -= 180
    elif a < -90:
        a += 180
    aa = abs(a)
    if aa < 20:
        return 0.0
    if aa > 70:
        return 90.0
    return a


TAG_MODES = ("Off", "Plot No. + Area", "Plot No.", "Area")


def _rect_corners(cx, cy, w, h, ang):
    th = math.radians(ang)
    c, sn = math.cos(th), math.sin(th)
    out = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        out.append((cx + dx * c - dy * sn, cy + dx * sn + dy * c))
    return out


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xin = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < xin:
                inside = not inside
        j = i
    return inside


def _dist_pt_seg(pt, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(pt[0] - ax, pt[1] - ay)
    t = max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / l2))
    return math.hypot(pt[0] - (ax + t * dx), pt[1] - (ay + t * dy))


def _box_fits(corners, poly, margin):
    n = len(poly)
    for c in corners:
        if not _point_in_poly(c, poly):
            return False
        for i in range(n):
            if _dist_pt_seg(c, poly[i], poly[(i + 1) % n]) < margin:
                return False
    return True


def _line_angle(dx, dy):
    """কর্ণের ঠিক কোণ (-90..90) - লেখা কর্ণের সমান্তরালে বসে।"""
    a = math.degrees(math.atan2(dy, dx))
    if a > 90:
        a -= 180
    elif a < -90:
        a += 180
    return a


def tag_variants(pi, area_sqft, mode):
    """প্লট নম্বর/শতকের লেখার তিনটি সংস্করণ (বড় → ছোট); জায়গা কম হলে ছোটটি বসে।"""
    sh = area_sqft / SQFT_PER_SHATAK
    want_no = mode in ("Plot No. + Area", "Plot No.")
    want_ar = mode in ("Plot No. + Area", "Area")
    triples = [(f"Plot {pi + 1}", f"{sh:.2f} Shatak"),
               (f"Plot {pi + 1}", f"{sh:.2f} Sh"),
               (f"#{pi + 1}", f"{sh:.2f}")]
    return [(n if want_no else None, a if want_ar else None) for n, a in triples]


def make_plot_tags(plot_tags, polys, plot_areas, mode, tf):
    """
    plot_tags : [{"pi", "anchor": (p, q), "diags": [(p, q), ...]}]  (ডাটা-কোঅর্ডিনেট)
    tf        : ডাটা পয়েন্ট -> স্ক্রিন/পেজ পয়েন্ট
    """
    out = []
    for tg in plot_tags or []:
        pi = tg["pi"]
        if pi >= len(polys):
            continue
        ap, aq = tg["anchor"]
        out.append({
            "poly": [tf(p) for p in polys[pi]],
            "anchor": (tf(ap), tf(aq)),
            "diags": [(tf(p), tf(q), dist(p, q)) for p, q in tg["diags"]],
            "variants": tag_variants(pi, plot_areas[pi] if pi < len(plot_areas) else 0.0, mode),
        })
    return out


def _layout_tag(tag, measure, u):
    """একটি প্লটের কর্ণ-দৈর্ঘ্য + প্লট নম্বর + শতক বসায়। জায়গা অনুযায়ী লেখা ছোট/সংক্ষিপ্ত করে।"""
    poly = tag["poly"]
    (p, q) = tag["anchor"]
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return []
    ang = _line_angle(dx, dy)
    th = math.radians(ang)
    ux, uy = math.cos(th), math.sin(th)
    nx, ny = -uy, ux
    if ny < -1e-9 or (abs(ny) < 1e-9 and nx < 0):
        nx, ny = -nx, -ny                       # প্লট নম্বর উপর/ডান দিকে, শতক নিচে/বাম দিকে
    mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
    diags = tag.get("diags") or []
    variants = tag.get("variants") or [(None, None)]
    if not diags and all(v == (None, None) for v in variants):
        return []

    def build(variant, sc):
        no_t, ar_t = variant
        specs, boxes = [], []
        h_len = 0.0
        for i, (dp1, dp2, ln) in enumerate(diags):
            t = 0.5 if len(diags) == 1 else (0.28 if i == 0 else 0.72)
            ddx, ddy = dp2[0] - dp1[0], dp2[1] - dp1[1]
            a2 = _line_angle(ddx, ddy)
            txt = f"{ln:.1f}'"
            w, h = measure(txt, "diag", sc)
            c = (dp1[0] + ddx * t, dp1[1] + ddy * t)
            specs.append({"text": txt, "center": c, "angle": a2, "kind": "diag", "bg": True, "scale": sc})
            boxes.append(_rect_corners(c[0], c[1], w + 6 * u * sc, h + 2 * u * sc, a2))
            if len(diags) == 1:
                h_len = h + 2 * u * sc
        gap = 1.5 * u * (0.5 + 0.5 * sc)
        base = (h_len / 2.0 if h_len else 1.0 * u) + gap
        items = []
        if no_t and ar_t:
            items = [(no_t, "tagno", 1), (ar_t, "tagarea", -1)]
        elif no_t:
            items = [(no_t, "tagno", 1)]
        elif ar_t:
            items = [(ar_t, "tagarea", 1)]
        for txt, kind, sign in items:
            w, h = measure(txt, kind, sc)
            d = base + h / 2.0
            c = (mx + sign * nx * d, my + sign * ny * d)
            specs.append({"text": txt, "center": c, "angle": ang, "kind": kind, "bg": False, "scale": sc})
            boxes.append(_rect_corners(c[0], c[1], w, h, ang))
        return specs, boxes

    order = []
    for vi, v in enumerate(variants):
        scs = [1.0, 0.9, 0.8, 0.7] if vi < len(variants) - 1 else [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        for sc in scs:
            order.append((v, sc))
    last = None
    for v, sc in order:
        specs, boxes = build(v, sc)
        last = specs
        margin = u * (2.0 + 3.0 * sc)
        if all(_box_fits(b, poly, margin) for b in boxes):
            return specs
    return last or []


def build_label_specs(spts, sides, part_segs, sub_segs, measure, u, tags=None):
    """
    spts      : চারটি কোণার স্ক্রিন/পেজ পয়েন্ট
    sides     : মূল চার বাহুর দৈর্ঘ্য
    part_segs : [(p, q, length)] বন্টন রেখা
    sub_segs  : [(p, q, length)] বন্টনকৃত বাহুর টুকরো
    measure   : (text, kind, scale=1.0) -> (width, height)
    u         : অফসেট ইউনিট (dp বা pt)
    tags      : make_plot_tags() এর ফলাফল (কর্ণের মান + প্লট নম্বর + শতক)
    ছোট প্লটে রেখার মান/ট্যাগ স্বয়ংক্রিয়ভাবে ছোট হয় যাতে একটার সাথে আরেকটা না লাগে।
    """
    specs = []
    n = len(spts)
    cx = sum(p[0] for p in spts) / n
    cy = sum(p[1] for p in spts) / n

    def place(p, q, text, kind, mode, dist_units, bg=False, t=0.5, fit=False):
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        tx, ty = dx / length, dy / length
        ang = label_angle(dx, dy)
        th = math.radians(ang)
        ux, uy = math.cos(th), math.sin(th)
        vx, vy = -uy, ux
        mx, my = p[0] + dx * t, p[1] + dy * t
        nx, ny = -ty, tx
        if nx * (mx - cx) + ny * (my - cy) < 0:
            nx, ny = -nx, -ny
        sc = 1.0
        if fit:
            w0, _h0 = measure(text, kind, 1.0)
            if w0 > 0:
                sc = max(0.4, min(1.0, 0.84 * length / w0))
        w, h = measure(text, kind, sc)
        if mode == "center":
            center = (mx, my)
        else:
            half = abs(nx * ux + ny * uy) * w / 2.0 + abs(nx * vx + ny * vy) * h / 2.0
            sign = 1.0 if mode == "out" else -1.0
            d = dist_units * u + half
            center = (mx + sign * nx * d, my + sign * ny * d)
        specs.append({"text": text, "center": center, "angle": ang, "kind": kind, "bg": bg, "scale": sc})

    for i in range(n):
        place(spts[i], spts[(i + 1) % n], f"{sides[i]:.1f}'", "side", "out", 9)

    # বন্টনকৃত বাহুর টুকরো ও বন্টন রেখার মান: রেখার দৈর্ঘ্য অনুযায়ী লেখার সাইজ ডায়নামিক
    for p, q, ln in sub_segs:
        place(p, q, f"{ln:.1f}'", "sub", "center", 0, bg=True, fit=True)

    for p, q, ln in part_segs:
        place(p, q, f"{ln:.1f}'", "cut", "center", 0, bg=True, fit=True)

    for tg in tags or []:
        specs.extend(_layout_tag(tg, measure, u))

    for i, v in enumerate(spts):
        dxv, dyv = v[0] - cx, v[1] - cy
        ln = math.hypot(dxv, dyv) or 1.0
        w, h = measure(f"P{i + 1}", "pt")
        d = 7 * u + 0.5 * math.hypot(w, h)
        specs.append({
            "text": f"P{i + 1}", "center": (v[0] + dxv / ln * d, v[1] + dyv / ln * d),
            "angle": 0.0, "kind": "pt", "bg": False, "scale": 1.0,
        })
    return specs


# ==========================================
# 2. File Export Utilities (DXF & PDF)
# ==========================================
def export_to_dxf(pts, partition_segments, full_filepath):
    dxf_content = ["0", "SECTION", "2", "ENTITIES"]
    n = len(pts)
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        dxf_content.extend([
            "0", "LINE", "8", "BOUNDARY",
            "10", str(p1[0]), "20", str(p1[1]), "30", "0.0",
            "11", str(p2[0]), "21", str(p2[1]), "31", "0.0"
        ])

    for seg in partition_segments:
        p_start, p_end = seg[0], seg[1]
        dxf_content.extend([
            "0", "LINE", "8", "PARTITIONS",
            "10", str(p_start[0]), "20", str(p_start[1]), "30", "0.0",
            "11", str(p_end[0]), "21", str(p_end[1]), "31", "0.0"
        ])

    dxf_content.extend(["0", "ENDSEC", "0", "EOF"])
    with open(full_filepath, "w") as f:
        f.write("\n".join(dxf_content))
    return os.path.abspath(full_filepath)


def parse_plot_groups(text):
    """summary টেক্সট থেকে (head_lines, [ {title, details, extras} ]) বের করে।"""
    head, groups = [], []
    for line in (text or "").split("\n"):
        if line.startswith("Plot ") and ": " in line and "sq.ft" in line:
            name, rest = line.split(": ", 1)
            parts = rest.split(" | ")
            groups.append({"title": f"{name}  -  {parts[0]}", "details": parts[1:], "extras": []})
        elif line.startswith(" ") and groups:
            groups[-1]["extras"].append(line.strip())
        elif not groups:
            head.append(line)
    return head, groups


def export_to_pdf(pts, sides, diag_val, diag_type, full_filepath, part_summary_text="",
                  partition_segments=None, sub_edge_segments=None, is_vertical=True, plot_polys=None,
                  plot_tags=None, plot_areas=None, tag_mode="Off"):
    c = canvas.Canvas(full_filepath, pagesize=letter)
    width, height = letter

    # ---- Header band ----
    c.setFillColorRGB(*C_PRIMARY[:3])
    c.rect(0, height - 66, width, 66, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 36, "Surveyor Juel - Land Measurement Report")
    c.setFillColorRGB(1.0, 0.85, 0.4)
    c.setFont("Helvetica", 9)
    c.drawString(50, height - 54, "Land Divider  |  Measurement  |  Report")

    text_object = c.beginText(50, height - 92)
    text_object.setFont("Helvetica-Bold", 11)
    text_object.setFillColorRGB(0.04, 0.38, 0.55)
    text_object.textLine("--- Boundary & Area Summary ---")
    text_object.setFont("Helvetica", 9.5)
    text_object.setFillColorRGB(0.1, 0.1, 0.1)

    total_area = polygon_area(pts)
    shatak = total_area / SQFT_PER_SHATAK
    text_object.textLine(f"North 1 (P1-P2): {sides[0]:.2f} ft   |   East 2 (P2-P3): {sides[1]:.2f} ft")
    text_object.textLine(f"South 3 (P3-P4): {sides[2]:.2f} ft   |   West 4 (P4-P1): {sides[3]:.2f} ft")
    text_object.textLine(f"Diagonal ({diag_type}): {diag_val:.2f} ft")
    text_object.setFont("Helvetica-Bold", 10)
    text_object.textLine(f"Total Area: {total_area:.2f} sq.ft ({shatak:.2f} Shatak)")
    text_object.textLine("")

    head_lines, plot_groups = parse_plot_groups(part_summary_text)
    if part_summary_text:
        text_object.setFont("Helvetica-Bold", 11)
        text_object.setFillColorRGB(0.52, 0.28, 0.78)
        text_object.textLine("--- Partition Summary ---")
        text_object.setFont("Helvetica", 9.5)
        text_object.setFillColorRGB(0.1, 0.1, 0.1)
        if plot_groups:
            for line in head_lines:
                text_object.textLine(line)
        else:
            lines = part_summary_text.split("\n")
            max_lines = 14
            if len(lines) > max_lines:
                extra = len(lines) - (max_lines - 1)
                lines = lines[:max_lines - 1] + [f"... (+{extra} more lines)"]
            for line in lines:
                text_object.textLine(line)

    c.drawText(text_object)
    bottom_y = text_object.getY()

    # ---- প্রতিটি প্লটের আলাদা রঙিন বক্স (২ কলাম) ----
    if plot_groups:
        margin_x, gap = 50.0, 12.0
        box_w = (width - 2 * margin_x - gap) / 2.0
        top = bottom_y - 2
        max_total = 285.0
        row_y = top
        rows_used_h = 0.0
        shown = 0
        i = 0
        while i < len(plot_groups):
            row = plot_groups[i:i + 2]
            heights = []
            for g_ in row:
                n_lines = 1 + (1 if g_["details"] else 0) + len(g_["extras"])
                heights.append(10 + 12 + 11 * (n_lines - 1))
            rh = max(heights)
            if rows_used_h + rh > max_total:
                break
            for k, g_ in enumerate(row):
                idx = i + k
                col = PLOT_COLORS[idx % len(PLOT_COLORS)]
                dark = (col[0] * 0.55, col[1] * 0.55, col[2] * 0.55)
                bx = margin_x + k * (box_w + gap)
                by = row_y - rh
                c.setFillColorRGB(col[0], col[1], col[2])
                c.setStrokeColorRGB(*dark)
                c.setLineWidth(1.2)
                c.roundRect(bx, by, box_w, rh, 6, fill=1, stroke=1)
                ty = row_y - 14
                c.setFillColorRGB(col[0] * 0.28, col[1] * 0.28, col[2] * 0.28)
                c.setFont("Helvetica-Bold", 9.5)
                c.drawString(bx + 8, ty, g_["title"])
                c.setFillColorRGB(0.1, 0.1, 0.1)
                c.setFont("Helvetica", 8.5)
                if g_["details"]:
                    ty -= 11
                    c.drawString(bx + 8, ty, "   |   ".join(g_["details"]))
                c.setFillColorRGB(0.75, 0.15, 0.02)
                c.setFont("Helvetica-Bold", 8.5)
                for ex in g_["extras"]:
                    ty -= 11
                    c.drawString(bx + 8, ty, ex)
                shown += 1
            row_y -= rh + 6
            rows_used_h += rh + 6
            i += 2
        bottom_y = row_y
        if shown < len(plot_groups):
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.setFont("Helvetica", 8.5)
            c.drawString(margin_x, bottom_y - 8, f"... (+{len(plot_groups) - shown} more plots not shown)")
            bottom_y -= 12

    title_y = bottom_y - 18
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0.04, 0.38, 0.55)
    c.drawString(50, title_y, "--- Graphic Plot Map (With All Dimension Values) ---")

    map_box_w = 500.0
    map_box_h = max(200.0, min(330.0, title_y - 20 - 75))
    map_center_x = width / 2
    map_center_y = title_y - 12 - map_box_h / 2

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w_data, h_data = max(1e-4, max_x - min_x), max(1e-4, max_y - min_y)
    scale = min((map_box_w - 150) / w_data, (map_box_h - 100) / h_data)
    cx_data, cy_data = (min_x + max_x) / 2, (min_y + max_y) / 2

    def to_pdf_coord(pt):
        return (map_center_x + (pt[0] - cx_data) * scale,
                map_center_y + (pt[1] - cy_data) * scale)

    pdf_pts = [to_pdf_coord(p) for p in pts]

    # ---- Fill plots ----
    polys = plot_polys if plot_polys else [pts]
    for i, poly in enumerate(polys):
        col = PLOT_COLORS[i % len(PLOT_COLORS)]
        c.setFillColorRGB(*col)
        path = c.beginPath()
        pp = [to_pdf_coord(p) for p in poly]
        path.moveTo(*pp[0])
        for q in pp[1:]:
            path.lineTo(*q)
        path.close()
        c.drawPath(path, fill=1, stroke=0)

    # ---- Diagonal ----
    if diag_val > 0:
        c.setStrokeColorRGB(0.95, 0.55, 0.15)
        c.setLineWidth(0.8)
        c.setDash(3, 3)
        if diag_type == "Pt 1-3":
            c.line(pdf_pts[0][0], pdf_pts[0][1], pdf_pts[2][0], pdf_pts[2][1])
        else:
            c.line(pdf_pts[1][0], pdf_pts[1][1], pdf_pts[3][0], pdf_pts[3][1])
        c.setDash()

    # ---- Partition lines ----
    part_screen = []
    if partition_segments:
        c.setStrokeColorRGB(*LABEL_COLORS["cut"][:3])
        c.setLineWidth(1.6)
        for seg in partition_segments:
            sp1, sp2 = to_pdf_coord(seg[0]), to_pdf_coord(seg[1])
            c.line(sp1[0], sp1[1], sp2[0], sp2[1])
            part_screen.append((sp1, sp2, dist(seg[0], seg[1])))

    sub_screen = []
    for p1, p2, _pos in (sub_edge_segments or []):
        sub_screen.append((to_pdf_coord(p1), to_pdf_coord(p2), dist(p1, p2)))

    if plot_tags:
        c.setStrokeColorRGB(*LABEL_COLORS["diag"][:3])
        c.setLineWidth(1.4)
        c.setDash(5, 3)
        for tg in plot_tags:
            for p1, p2 in tg["diags"]:
                q1, q2 = to_pdf_coord(p1), to_pdf_coord(p2)
                c.line(q1[0], q1[1], q2[0], q2[1])
        c.setDash()
    tags_pdf = make_plot_tags(plot_tags, polys, plot_areas or [], tag_mode, to_pdf_coord)

    # ---- Boundary ----
    c.setStrokeColorRGB(0.0, 0.42, 0.40)
    c.setLineWidth(2.2)
    n = len(pdf_pts)
    for i in range(n):
        p1, p2 = pdf_pts[i], pdf_pts[(i + 1) % n]
        c.line(p1[0], p1[1], p2[0], p2[1])
    c.setFillColorRGB(0.0, 0.5, 0.4)
    for p in pdf_pts:
        c.circle(p[0], p[1], 3, fill=1, stroke=0)

    # ---- Labels ----
    def measure(text, kind, scale=1.0):
        size = LABEL_BASE_SIZE[kind] * scale
        return stringWidth(text, "Helvetica-Bold", size), size

    specs = build_label_specs(pdf_pts, sides, part_screen, sub_screen, measure, 1.0, tags_pdf)
    for spec in specs:
        size = LABEL_BASE_SIZE[spec["kind"]] * spec.get("scale", 1.0)
        w, h = measure(spec["text"], spec["kind"], spec.get("scale", 1.0))
        cxs, cys = spec["center"]
        c.saveState()
        c.translate(cxs, cys)
        c.rotate(spec["angle"])
        if spec["bg"]:
            c.setFillColorRGB(1, 1, 1)
            c.roundRect(-w / 2 - 2, -h / 2 - 1, w + 4, h + 3, 2, fill=1, stroke=0)
        col = LABEL_COLORS[spec["kind"]]
        c.setFillColorRGB(*col[:3])
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(0, -size * 0.33, spec["text"])
        c.restoreState()

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(50, 40, "Developed by: Md. Juel Badsha | Mobile: +8801744431272")
    c.drawRightString(width - 50, 40, "Surveyor Juel Land App")

    c.save()
    return os.path.abspath(full_filepath)


# ==========================================
# 3. Interactive Map Canvas Component
# ==========================================
class MapCanvasWidget(StencilView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pts = []
        self.div_lines = []
        self.partition_segments = []
        self.sub_edge_segments = []
        self.plot_polys = []
        self.plot_tags = []
        self.plot_areas = []
        self.tag_mode = "Off"
        self.diag_val = 0.0
        self.diag_type = "Pt 1-3"
        self.part_area = 0.0
        self.sides = []
        self.is_vertical = True

        self.zoom_scale = 1.0
        self.min_zoom = 0.4
        self.max_zoom = 4.5

        self.pan_x = 0.0
        self.pan_y = 0.0
        self.last_touch_pos = None
        self.bind(size=self.trigger_redraw, pos=self.trigger_redraw)

    def draw_map(self, pts, sides, diag_val=0.0, diag_type="Pt 1-3", div_lines=None, part_area=0.0,
                 is_vertical=True, partition_segments=None, sub_edge_segments=None, plot_polys=None,
                 plot_tags=None, plot_areas=None, tag_mode="Off"):
        self.pts = pts
        self.sides = sides
        self.diag_val = diag_val
        self.diag_type = diag_type
        self.div_lines = div_lines if div_lines else []
        self.partition_segments = partition_segments if partition_segments else []
        self.sub_edge_segments = sub_edge_segments if sub_edge_segments else []
        self.plot_polys = plot_polys if plot_polys else []
        self.plot_tags = plot_tags if plot_tags else []
        self.plot_areas = plot_areas if plot_areas else []
        self.tag_mode = tag_mode
        self.part_area = part_area
        self.is_vertical = is_vertical
        self.trigger_redraw()

    def clear_canvas(self):
        self.pts, self.sides, self.div_lines = [], [], []
        self.partition_segments, self.sub_edge_segments, self.plot_polys = [], [], []
        self.plot_tags, self.plot_areas, self.tag_mode = [], [], "Off"
        self.diag_val = 0.0
        self.part_area = 0.0
        self.zoom_scale = 1.0
        self.pan_x, self.pan_y = 0.0, 0.0
        self.canvas.clear()

    def zoom_in(self, *args):
        new_scale = self.zoom_scale * 1.25
        if new_scale <= self.max_zoom:
            self.zoom_scale = new_scale
            self.trigger_redraw()

    def zoom_out(self, *args):
        new_scale = self.zoom_scale / 1.25
        if new_scale >= self.min_zoom:
            self.zoom_scale = new_scale
            self.trigger_redraw()

    def reset_zoom(self, *args):
        self.zoom_scale = 1.0
        self.pan_x, self.pan_y = 0.0, 0.0
        self.trigger_redraw()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.last_touch_pos = touch.pos
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self and self.last_touch_pos:
            dx = touch.x - self.last_touch_pos[0]
            dy = touch.y - self.last_touch_pos[1]
            self.pan_x += dx
            self.pan_y += dy
            self.last_touch_pos = touch.pos
            self.trigger_redraw()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.last_touch_pos = None
            return True
        return super().on_touch_up(touch)

    def trigger_redraw(self, *args):
        Clock.unschedule(self.redraw)
        Clock.schedule_once(self.redraw, 0.05)

    # ---- text helpers ----
    def _font_px(self, kind, scale=1.0):
        return sp(LABEL_BASE_SIZE[kind] * (0.6 + 0.4 * self.zoom_scale) * scale)

    def _texture(self, text, kind, scale=1.0):
        core_lbl = CoreLabel(text=str(text), font_size=max(5, self._font_px(kind, scale)), bold=True)
        core_lbl.refresh()
        return core_lbl.texture

    def _measure(self, text, kind, scale=1.0):
        try:
            return self._texture(text, kind, scale).size
        except Exception:
            return (dp(30) * scale, dp(12) * scale)

    def draw_spec(self, spec):
        try:
            sc = spec.get("scale", 1.0)
            tex = self._texture(spec["text"], spec["kind"], sc)
            w, h = tex.size
            cx, cy = spec["center"]
            PushMatrix()
            Rotate(angle=spec["angle"], origin=(cx, cy))
            if spec["bg"]:
                Color(1, 1, 1, 0.92)
                RoundedRectangle(pos=(cx - w / 2 - dp(3) * sc, cy - h / 2 - dp(1) * sc),
                                 size=(w + dp(6) * sc, h + dp(2) * sc), radius=[dp(3)])
            Color(*LABEL_COLORS[spec["kind"]])
            Rectangle(texture=tex, pos=(cx - w / 2, cy - h / 2), size=(w, h))
            PopMatrix()
        except Exception:
            pass

    def redraw(self, dt=None):
        self.canvas.clear()
        if not self.pts or len(self.pts) < 4:
            return

        try:
            with self.canvas:
                Color(0.99, 0.99, 1, 1)
                Rectangle(pos=self.pos, size=self.size)

                Color(0.55, 0.70, 0.85, 1)
                Line(rectangle=(self.x, self.y, self.width, self.height), width=1.2)

                xs, ys = [p[0] for p in self.pts], [p[1] for p in self.pts]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                w_data, h_data = max(1e-4, max_x - min_x), max(1e-4, max_y - min_y)
                padding_x, padding_y = dp(70), dp(55)

                if self.width <= 2 * padding_x or self.height <= 2 * padding_y:
                    return

                base_scale = min(
                    (self.width - 2 * padding_x) / w_data,
                    (self.height - 2 * padding_y) / h_data,
                )
                scale = base_scale * self.zoom_scale

                cx_screen = self.x + self.width / 2 + self.pan_x
                cy_screen = self.y + self.height / 2 + self.pan_y
                cx_data, cy_data = (min_x + max_x) / 2, (min_y + max_y) / 2

                def to_screen(pt):
                    return (cx_screen + (pt[0] - cx_data) * scale,
                            cy_screen + (pt[1] - cy_data) * scale)

                screen_pts = [to_screen(p) for p in self.pts]

                # ---- plot fills ----
                polys = self.plot_polys if self.plot_polys else [self.pts]
                for i, poly in enumerate(polys):
                    col = PLOT_COLORS[i % len(PLOT_COLORS)]
                    Color(col[0], col[1], col[2], 1)
                    flat = []
                    for p in poly:
                        sp_ = to_screen(p)
                        flat.extend([sp_[0], sp_[1]])
                    try:
                        Quad(points=flat)
                    except Exception:
                        pass

                # ---- diagonal ----
                if self.diag_val > 0:
                    Color(0.95, 0.50, 0.10, 0.45)
                    if self.diag_type == "Pt 1-3":
                        Line(points=[screen_pts[0][0], screen_pts[0][1], screen_pts[2][0], screen_pts[2][1]],
                             width=1.1, dash_length=dp(5), dash_offset=dp(3))
                    else:
                        Line(points=[screen_pts[1][0], screen_pts[1][1], screen_pts[3][0], screen_pts[3][1]],
                             width=1.1, dash_length=dp(5), dash_offset=dp(3))

                # ---- partition lines ----
                part_screen = []
                Color(*LABEL_COLORS["cut"][:3], 1)
                for seg in self.partition_segments:
                    sp1, sp2 = to_screen(seg[0]), to_screen(seg[1])
                    Line(points=[sp1[0], sp1[1], sp2[0], sp2[1]], width=dp(1.6))
                    part_screen.append((sp1, sp2, dist(seg[0], seg[1])))

                # ---- selected plot diagonals ----
                for tg in self.plot_tags:
                    for dp1, dp2 in tg["diags"]:
                        q1, q2 = to_screen(dp1), to_screen(dp2)
                        Color(*LABEL_COLORS["diag"])
                        Line(points=[q1[0], q1[1], q2[0], q2[1]], width=dp(1.8),
                             dash_length=dp(7), dash_offset=dp(4))
                tags_screen = make_plot_tags(self.plot_tags, polys, self.plot_areas,
                                             self.tag_mode, to_screen)

                # ---- boundary ----
                Color(0.0, 0.42, 0.40, 1)
                flat_pts = []
                for sp_pt in screen_pts:
                    flat_pts.extend([sp_pt[0], sp_pt[1]])
                flat_pts.extend([screen_pts[0][0], screen_pts[0][1]])
                Line(points=flat_pts, width=dp(2))

                offset_factor = 0.7 + 0.3 * self.zoom_scale
                Color(0.0, 0.55, 0.45, 1)
                dot_size = dp(8) * min(2.5, max(0.8, offset_factor))
                for sp_pt in screen_pts:
                    Ellipse(pos=(sp_pt[0] - dot_size / 2, sp_pt[1] - dot_size / 2), size=(dot_size, dot_size))

                # ---- labels ----
                sub_screen = []
                for p1, p2, _pos in self.sub_edge_segments:
                    sub_screen.append((to_screen(p1), to_screen(p2), dist(p1, p2)))

                specs = build_label_specs(
                    screen_pts, self.sides, part_screen, sub_screen,
                    self._measure, dp(1) * offset_factor, tags_screen
                )
                for spec in specs:
                    self.draw_spec(spec)

        except Exception as e:
            print("Redraw Exception Handled:", e)


# ==========================================
# 4a. Styled UI Components
# ==========================================
class Card(BoxLayout):
    """গোল কোণাযুক্ত রঙিন কার্ড"""

    def __init__(self, bg=(1, 1, 1, 1), border=None, radius=14, **kwargs):
        super().__init__(**kwargs)
        self._radius = dp(radius)
        self._border = None
        with self.canvas.before:
            Color(*bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            if border:
                Color(*border)
                self._border = Line(
                    rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius),
                    width=dp(1.3)
                )
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        if self._border is not None:
            self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


def attach_round_bg(w, bg, radius):
    with w.canvas.before:
        w._bg_color = Color(*bg)
        w._bg_rect = RoundedRectangle(pos=w.pos, size=w.size, radius=[dp(radius)])

    def upd(*a):
        w._bg_rect.pos = w.pos
        w._bg_rect.size = w.size

    def restyle(*a):
        if w.disabled:
            w._bg_color.rgba = (bg[0], bg[1], bg[2], 0.40)
        elif w.state == "down":
            w._bg_color.rgba = (bg[0] * 0.72, bg[1] * 0.72, bg[2] * 0.72, bg[3])
        else:
            w._bg_color.rgba = bg

    w.bind(pos=upd, size=upd, state=restyle, disabled=restyle)
    restyle()


class RoundedButton(Button):
    def __init__(self, bg=(0.1, 0.5, 0.4, 1), radius=12, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs["background_color"] = (0, 0, 0, 0)
        kwargs.setdefault("color", (1, 1, 1, 1))
        kwargs.setdefault("bold", True)
        super().__init__(**kwargs)
        attach_round_bg(self, bg, radius)


class ColorOption(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0.96, 0.94, 1.0, 1)
        self.color = C_TEXT
        self.font_size = sp(14)


class RoundedSpinner(Spinner):
    def __init__(self, bg=(0.5, 0.3, 0.8, 1), radius=12, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs["background_color"] = (0, 0, 0, 0)
        kwargs.setdefault("color", (1, 1, 1, 1))
        kwargs.setdefault("bold", True)
        kwargs["option_cls"] = ColorOption
        super().__init__(**kwargs)
        attach_round_bg(self, bg, radius)


def left_label(text, color=C_TEXT, size=13, bold=False, markup=False):
    lbl = Label(text=text, color=color, font_size=sp(size), bold=bold,
                halign="left", valign="middle", markup=markup)
    lbl.bind(size=lbl.setter("text_size"))
    return lbl


def auto_height_label(text, color=C_TEXT, size=13, bold=False, min_h=30, markup=False):
    lbl = Label(text=text, color=color, font_size=sp(size), bold=bold, markup=markup,
                halign="left", valign="top", size_hint_y=None, height=dp(min_h))
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, s: setattr(inst, "height", max(dp(min_h), s[1] + dp(3))))
    return lbl


# ==========================================
# 4b. Main Application Interface
# ==========================================
class SSRKLandApp(App):
    ADJ_STEP = 0.5  # + / - বাটনে প্রতিবার কত ফুট কম-বেশি হবে
    DEFAULT_ADJ_MSG = "Divide a plot first to enable side adjustment."

    # ---------- small UI factories ----------
    def make_card(self, accent):
        card = Card(bg=(1, 1, 1, 1), border=accent, orientation="vertical",
                    padding=dp(8), spacing=dp(5), size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))
        return card

    def section_header(self, card, text, color):
        hdr = Card(bg=color, radius=10, size_hint_y=None, height=dp(32),
                   padding=[dp(12), 0, dp(12), 0])
        lbl = left_label(text, color=(1, 1, 1, 1), size=14, bold=True)
        hdr.add_widget(lbl)
        card.add_widget(hdr)

    def field(self, inp, color, size_hint_x=1):
        box = Card(bg=(0.985, 0.99, 1, 1), border=color, radius=10, size_hint_x=size_hint_x,
                   padding=[dp(2), dp(2), dp(2), dp(2)])
        box.add_widget(inp)
        return box

    def create_input(self, default_val, bound=True):
        inp = TextInput(
            text=default_val, multiline=False, input_filter="float",
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
            foreground_color=C_TEXT, cursor_color=C_PRIMARY, font_size=sp(15),
            padding=[dp(10), dp(8), dp(10), dp(4)]
        )
        if bound:
            inp.bind(text=self.on_side_input_change)
        return inp

    # ---------- build ----------
    def build(self):
        self.title = "Surveyor Juel - Land Divider"
        self.last_partition_info = ""
        self.adjuster = None
        self.adj_ctx = {}
        self.adj_k = 0
        self._adj_lock = False
        self._adj_event = None
        self._area_event = None

        root_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(4))
        main_layout = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(14), size_hint_y=None)
        main_layout.bind(minimum_height=main_layout.setter("height"))

        # ---------- Header ----------
        header = Card(bg=C_PRIMARY, radius=18, orientation="vertical", size_hint_y=None,
                      height=dp(68), padding=[dp(12), dp(6), dp(12), dp(6)], spacing=dp(1))
        header.add_widget(Label(
            text="[b]Surveyor Juel[/b]", markup=True, color=(1, 1, 1, 1), font_size=sp(25)
        ))
        header.add_widget(Label(
            text="Land Divider  •  Measurement  •  Report",
            color=(1.0, 0.86, 0.42, 1), font_size=sp(12)
        ))
        main_layout.add_widget(header)

        # ---------- 1. Boundary ----------
        card1 = self.make_card(C_BLUE)
        self.section_header(card1, "1   Boundary Sides & Diagonal", C_BLUE)

        grid_inputs = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                                 row_default_height=dp(38), row_force_default=True)
        grid_inputs.bind(minimum_height=grid_inputs.setter("height"))

        side_specs = [
            ("North 1 (Pt 1-2):", "165", C_GREEN, "txt_s1"),
            ("East 2 (Pt 2-3):", "97", C_ORANGE, "txt_s2"),
            ("South 3 (Pt 3-4):", "122", C_PURPLE, "txt_s3"),
            ("West 4 (Pt 4-1):", "96", C_RED, "txt_s4"),
        ]
        for text, default, col, attr in side_specs:
            grid_inputs.add_widget(left_label(text, color=col, size=14, bold=True))
            inp = self.create_input(default)
            setattr(self, attr, inp)
            grid_inputs.add_widget(self.field(inp, col))
        card1.add_widget(grid_inputs)

        diag_box = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
        self.spn_diag_type = RoundedSpinner(
            text="Pt 1-3", values=("Pt 1-3", "Pt 2-4"),
            size_hint_x=0.4, font_size=sp(14), bg=C_TEAL
        )
        self.spn_diag_type.bind(text=self.on_side_input_change)
        diag_box.add_widget(self.spn_diag_type)
        self.txt_diag = self.create_input("172.45")
        diag_box.add_widget(self.field(self.txt_diag, C_TEAL, size_hint_x=0.6))
        card1.add_widget(diag_box)

        self.lbl_ref_bounds = auto_height_label(
            "Reference Diagonal Limits: --", color=C_BLUE, size=12, bold=True, min_h=26)
        card1.add_widget(self.lbl_ref_bounds)

        act_box = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
        btn_calc = RoundedButton(text="Generate Land Map", bg=C_GREEN, size_hint_x=0.68, font_size=sp(15))
        btn_calc.bind(on_press=self.on_calculate)
        act_box.add_widget(btn_calc)
        btn_reset = RoundedButton(text="Reset", bg=C_RED, size_hint_x=0.32, font_size=sp(14))
        btn_reset.bind(on_press=self.on_reset)
        act_box.add_widget(btn_reset)
        card1.add_widget(act_box)
        main_layout.add_widget(card1)

        # ---------- Total area banner ----------
        banner = Card(bg=(0.88, 0.97, 0.91, 1), border=C_GREEN, radius=14,
                      size_hint_y=None, height=dp(48), padding=[dp(8), 0, dp(8), 0])
        self.lbl_area = Label(
            text="Total Area: 0.00 sq.ft (0.00 Shatak)", color=(0.0, 0.40, 0.25, 1),
            bold=True, font_size=sp(15)
        )
        banner.add_widget(self.lbl_area)
        main_layout.add_widget(banner)

        # ---------- Map ----------
        map_card = Card(bg=(1, 1, 1, 1), border=C_PRIMARY, radius=14,
                        size_hint_y=None, height=dp(430), padding=dp(4))
        map_container = FloatLayout()
        self.map_widget = MapCanvasWidget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        map_container.add_widget(self.map_widget)

        zoom_box = BoxLayout(
            orientation="vertical", spacing=dp(6),
            size_hint=(None, None), size=(dp(42), dp(138)),
            pos_hint={"right": 0.98, "y": 0.03}
        )
        for txt, handler, col in (("+", self.map_widget.zoom_in, (0.04, 0.38, 0.55, 0.92)),
                                  ("R", self.map_widget.reset_zoom, (0.96, 0.50, 0.10, 0.92)),
                                  ("-", self.map_widget.zoom_out, (0.04, 0.38, 0.55, 0.92))):
            b = RoundedButton(text=txt, bg=col, radius=10, font_size=sp(18))
            b.bind(on_press=handler)
            zoom_box.add_widget(b)
        map_container.add_widget(zoom_box)
        map_card.add_widget(map_container)
        main_layout.add_widget(map_card)

        # ---------- 2. Partition ----------
        card2 = self.make_card(C_PURPLE)
        self.section_header(card2, "2   Partition Settings", C_PURPLE)

        opt_grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                              row_default_height=dp(38), row_force_default=True)
        opt_grid.bind(minimum_height=opt_grid.setter("height"))

        opt_grid.add_widget(left_label("Mode:", size=14, bold=True, color=C_PURPLE))
        self.spn_mode = RoundedSpinner(
            text="By Shatak", values=("By Shatak", "By Sq.Ft", "Equal Division"),
            bg=C_PURPLE, font_size=sp(14)
        )
        opt_grid.add_widget(self.spn_mode)
        self.spn_mode.bind(text=self.on_mode_change)

        opt_grid.add_widget(left_label("Parts (plots):", size=14, bold=True, color=C_BLUE))
        self.txt_parts = self.create_input("1", bound=False)
        opt_grid.add_widget(self.field(self.txt_parts, C_BLUE))

        self.lbl_value = left_label("Value (Shatak):", size=14, bold=True, color=C_ORANGE)
        opt_grid.add_widget(self.lbl_value)
        self.txt_part_val = self.create_input("1", bound=False)
        self.box_part_val = self.field(self.txt_part_val, C_ORANGE)
        opt_grid.add_widget(self.box_part_val)

        opt_grid.add_widget(left_label("Direction:", size=14, bold=True, color=C_BLUE))
        self.spn_dir = RoundedSpinner(
            text="West to East", values=("West to East", "East to West", "North to South", "South to North"),
            bg=C_BLUE, font_size=sp(14)
        )
        opt_grid.add_widget(self.spn_dir)

        opt_grid.add_widget(left_label("Cut Line:", size=14, bold=True, color=C_TEAL))
        self.spn_cutstyle = RoundedSpinner(
            text="Parallel to Start Edge", values=("Parallel to Start Edge", "Straight (Map Axis)"),
            bg=C_TEAL, font_size=sp(13)
        )
        opt_grid.add_widget(self.spn_cutstyle)
        card2.add_widget(opt_grid)

        btn_box = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(42))
        btn_divide = RoundedButton(text="Divide Plot", bg=C_GREEN, font_size=sp(14), size_hint_x=0.36)
        btn_divide.bind(on_press=self.on_divide)
        btn_box.add_widget(btn_divide)
        btn_export = RoundedButton(text="Export CAD", bg=C_BLUE, font_size=sp(13), size_hint_x=0.32)
        btn_export.bind(on_press=self.on_export_cad)
        btn_box.add_widget(btn_export)
        btn_pdf = RoundedButton(text="Export PDF", bg=C_ORANGE, font_size=sp(13), size_hint_x=0.32)
        btn_pdf.bind(on_press=self.on_export_pdf)
        btn_box.add_widget(btn_pdf)
        main_layout.add_widget(card2)
        card2b = self.make_card(C_GREEN)
        card2b.add_widget(btn_box)
        main_layout.add_widget(card2b)

        # ---------- 3. Adjust ----------
        card3 = self.make_card(C_ORANGE)
        self.section_header(card3, "3   Adjust Adjacent Sides (Area fixed)", C_ORANGE)

        self.lbl_adj_ref = auto_height_label(self.DEFAULT_ADJ_MSG, color=C_BLUE, size=12, bold=True, min_h=40)
        card3.add_widget(self.lbl_adj_ref)

        cut_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
        cut_row.add_widget(left_label("Adjust plot:", size=13, bold=True, color=C_PURPLE))
        self.spn_cut = RoundedSpinner(text="Plot 1", values=("Plot 1",), bg=C_PURPLE, font_size=sp(14))
        self.spn_cut.bind(text=self.on_cut_select)
        cut_row.add_widget(self.spn_cut)
        card3.add_widget(cut_row)

        def make_adj_row(which, color):
            row = BoxLayout(orientation="horizontal", spacing=dp(5), size_hint_y=None, height=dp(40))
            name_lbl = left_label("-- --", size=12, bold=True, color=color)
            name_lbl.size_hint_x = 0.30
            btn_minus = RoundedButton(text="-", size_hint_x=0.13, font_size=sp(20), bg=C_RED, radius=10)
            inp = self.create_input("", bound=False)
            inp.bind(text=partial(self.on_adj_text, which))
            box = self.field(inp, color, size_hint_x=0.70)
            btn_plus = RoundedButton(text="+", size_hint_x=0.13, font_size=sp(20), bg=C_GREEN, radius=10)
            btn_minus.bind(on_press=partial(self.on_adj_step, which, -self.ADJ_STEP))
            btn_plus.bind(on_press=partial(self.on_adj_step, which, self.ADJ_STEP))
            for w in (name_lbl, box):
                row.add_widget(w)
            return row, name_lbl, inp, btn_minus, btn_plus

        row_a, self.lbl_adj_a_name, self.txt_adj_a, self.btn_adj_a_minus, self.btn_adj_a_plus = make_adj_row("a", C_GREEN)
        row_b, self.lbl_adj_b_name, self.txt_adj_b, self.btn_adj_b_minus, self.btn_adj_b_plus = make_adj_row("b", C_PURPLE)
        card3.add_widget(row_a)
        card3.add_widget(row_b)

        main_layout.add_widget(card3)

        # ---------- 4. Change Plot Area (আলাদা বক্স) ----------
        card_area = self.make_card(C_RED)
        self.section_header(card_area, "4   Change Plot Area", C_RED)
        area_pick = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
        area_pick.add_widget(left_label("Area of plot:", size=13, bold=True, color=C_RED))
        self.spn_area_plot = RoundedSpinner(text="Plot 1", values=("Plot 1",), bg=C_RED, font_size=sp(14))
        self.spn_area_plot.bind(text=self.on_area_plot_select)
        area_pick.add_widget(self.spn_area_plot)
        card_area.add_widget(area_pick)

        def make_area_row(label, color, unit):
            row = BoxLayout(orientation="horizontal", spacing=dp(5), size_hint_y=None, height=dp(40))
            lbl = left_label(label, size=12, bold=True, color=color)
            lbl.size_hint_x = 0.30
            btn_m = RoundedButton(text="-", size_hint_x=0.13, font_size=sp(20), bg=C_RED, radius=10)
            inp = self.create_input("", bound=False)
            inp.bind(text=partial(self.on_area_text, unit))
            box = self.field(inp, color, size_hint_x=0.70)
            btn_p = RoundedButton(text="+", size_hint_x=0.13, font_size=sp(20), bg=C_GREEN, radius=10)
            btn_m.bind(on_press=partial(self.on_area_step, unit, -1))
            btn_p.bind(on_press=partial(self.on_area_step, unit, 1))
            for w in (lbl, box):
                row.add_widget(w)
            return row, inp, btn_m, btn_p

        row_sq, self.txt_area_sqft, self.btn_sq_m, self.btn_sq_p = make_area_row("Sq.Ft", C_ORANGE, "sqft")
        row_sh, self.txt_area_shatak, self.btn_sh_m, self.btn_sh_p = make_area_row("Shatak", C_TEAL, "shatak")
        card_area.add_widget(row_sq)
        card_area.add_widget(row_sh)
        main_layout.add_widget(card_area)

        # ---- 4. Plot Diagonal ----
        card4 = self.make_card(C_TEAL)
        self.section_header(card4, "5   Plot Diagonal (draw & measure)", C_TEAL)
        pd_grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                             row_default_height=dp(36), row_force_default=True)
        pd_grid.bind(minimum_height=pd_grid.setter("height"))
        pd_grid.add_widget(left_label("Select plot:", size=13, bold=True, color=C_TEAL))
        self.spn_pd_plot = RoundedSpinner(text="Off", values=("Off",), bg=C_TEAL, font_size=sp(14))
        self.spn_pd_plot.bind(text=self.on_pd_change)
        pd_grid.add_widget(self.spn_pd_plot)
        pd_grid.add_widget(left_label("Diagonal:", size=13, bold=True, color=C_ORANGE))
        self.spn_pd_type = RoundedSpinner(text="NW-SE", values=("NW-SE", "NE-SW", "Both"),
                                          bg=C_ORANGE, font_size=sp(14))
        self.spn_pd_type.bind(text=self.on_pd_change)
        pd_grid.add_widget(self.spn_pd_type)
        card4.add_widget(pd_grid)
        self.lbl_pd_info = auto_height_label("Divide a plot, then select a plot to see its diagonal.",
                                             color=C_BLUE, size=12, bold=True, min_h=26)
        main_layout.add_widget(card4)

        # ---- 5b. Plot No. & Area on map ----
        card5 = self.make_card(C_BLUE)
        self.section_header(card5, "6   Plot No. & Area on Map", C_BLUE)
        tg_grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                             row_default_height=dp(36), row_force_default=True)
        tg_grid.bind(minimum_height=tg_grid.setter("height"))
        tg_grid.add_widget(left_label("Show:", size=13, bold=True, color=C_BLUE))
        self.spn_tag_mode = RoundedSpinner(text="Off", values=TAG_MODES, bg=C_BLUE, font_size=sp(14))
        self.spn_tag_mode.bind(text=self.on_pd_change)
        tg_grid.add_widget(self.spn_tag_mode)
        card5.add_widget(tg_grid)
        card5.add_widget(auto_height_label(
            "Plot number and Shatak appear on opposite sides of each plot's diagonal.",
            color=C_BLUE, size=12, bold=True, min_h=26))
        main_layout.add_widget(card5)
        self.set_adjust_enabled(False)

        # ---------- Output ----------
        out_card = Card(bg=(1.0, 0.98, 0.88, 1), border=(0.95, 0.75, 0.2, 1), radius=14,
                        orientation="vertical", padding=dp(8), spacing=dp(3), size_hint_y=None)
        out_card.bind(minimum_height=out_card.setter("height"))
        out_card.add_widget(left_label("Summary", size=13, bold=True, color=C_ORANGE))
        out_card.children[0].size_hint_y = None
        out_card.children[0].height = dp(22)
        self.lbl_output = auto_height_label("Calculation summary...", color=C_TEXT, size=13, min_h=40)
        out_card.add_widget(self.lbl_output)
        self.plot_boxes = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None)
        self.plot_boxes.bind(minimum_height=self.plot_boxes.setter("height"))
        self.plot_boxes.height = 0
        out_card.add_widget(self.plot_boxes)
        main_layout.add_widget(out_card)

        # ---------- Footer ----------
        developer_info_text = (
            "[b][color=FFD54F]Developed by[/color][/b]\n"
            "[b][color=FFFFFF]Md: Juel Badsha[/color][/b]\n"
            "[color=B2EBF2]Address: Amrulbari polipara, Thana: Badargonj, Zilla: Rangpur, Bangladesh[/color]\n"
            "[b][color=FFAB91]Mobile no: +8801744431272[/color][/b]"
        )
        footer = Card(bg=C_PRIMARY, radius=16, size_hint_y=None, height=dp(120), padding=dp(10))
        dev_label = Label(text=developer_info_text, markup=True, halign="center", valign="middle",
                          font_size=sp(13))
        dev_label.bind(size=dev_label.setter("text_size"))
        footer.add_widget(dev_label)
        main_layout.add_widget(footer)

        root_scroll.add_widget(main_layout)
        self.on_side_input_change()
        return root_scroll

    def on_side_input_change(self, *args):
        try:
            s1 = float(self.txt_s1.text) if self.txt_s1.text.strip() else 0.0
            s2 = float(self.txt_s2.text) if self.txt_s2.text.strip() else 0.0
            s3 = float(self.txt_s3.text) if self.txt_s3.text.strip() else 0.0
            s4 = float(self.txt_s4.text) if self.txt_s4.text.strip() else 0.0

            if s1 <= 0 or s2 <= 0 or s3 <= 0 or s4 <= 0:
                self.lbl_ref_bounds.text = "Reference Diagonal Limits: Please enter valid positive numbers"
                self.lbl_ref_bounds.color = (0.8, 0.3, 0.0, 1)
                return

            diag_type = self.spn_diag_type.text
            min_d, max_d = get_diagonal_bounds(s1, s2, s3, s4, diag_type)
            self.lbl_ref_bounds.text = f"Allowed {diag_type} Diagonal: {min_d:.2f} ft to {max_d:.2f} ft"
            self.lbl_ref_bounds.color = (0.0, 0.5, 0.2, 1)
        except Exception:
            self.lbl_ref_bounds.text = "Reference Diagonal Limits: Incomplete or invalid inputs"
            self.lbl_ref_bounds.color = (0.8, 0.3, 0.0, 1)

    def get_inputs(self):
        try:
            s1_text = self.txt_s1.text.strip()
            s2_text = self.txt_s2.text.strip()
            s3_text = self.txt_s3.text.strip()
            s4_text = self.txt_s4.text.strip()
            diag_text = self.txt_diag.text.strip()

            if not all([s1_text, s2_text, s3_text, s4_text, diag_text]):
                raise ValueError("All side and diagonal fields must be filled.")

            s1 = float(s1_text)
            s2 = float(s2_text)
            s3 = float(s3_text)
            s4 = float(s4_text)
            diag_val = float(diag_text)

            if any(v <= 0 for v in [s1, s2, s3, s4, diag_val]):
                raise ValueError("All dimensions must be greater than zero.")

            diag_type = self.spn_diag_type.text
            return s1, s2, s3, s4, diag_val, diag_type
        except ValueError as ve:
            self.lbl_output.text = f"Input Error: {str(ve)}"
            return None
        except Exception as e:
            self.lbl_output.text = f"Input Error: Please check your entered values ({str(e)})"
            return None

    def on_calculate(self, instance):
        vals = self.get_inputs()
        if not vals:
            return

        s1, s2, s3, s4, diag_val, diag_type = vals
        try:
            pts = calculate_quadrilateral(s1, s2, s3, s4, diag_val, diag_type)
            area = polygon_area(pts)
            shatak = area / SQFT_PER_SHATAK

            self.last_partition_info = ""
            self.clear_adjust()
            self.lbl_area.text = f"Total Area: {area:.2f} sq.ft ({shatak:.2f} Shatak)"
            self.map_widget.draw_map(pts, [s1, s2, s3, s4], diag_val=diag_val, diag_type=diag_type)
            self.lbl_output.text = f"Success! Land Boundary Created.\nUsing Diagonal: {diag_type}\nTotal Area: {area:.2f} sq.ft | {shatak:.2f} Shatak"
        except ValueError as ve:
            self.lbl_output.text = f"Geometry Limit Error:\n{str(ve)}"
        except Exception as e:
            self.lbl_output.text = f"Calculation Error: {str(e)}"

    def on_mode_change(self, instance, text):
        if text == "By Shatak":
            self.lbl_value.text = "Value (Shatak):"
        elif text == "By Sq.Ft":
            self.lbl_value.text = "Value (Sq.Ft):"
        else:
            self.lbl_value.text = "Value (not used):"
        self.txt_part_val.disabled = (text == "Equal Division")
        self.box_part_val.opacity = 0.45 if text == "Equal Division" else 1.0

    def read_division_params(self, pts):
        """Mode/Parts/Value ঘর থেকে বন্টনের তথ্য পড়ে।
        ফেরত: (target_sqft, num_parts, max_cuts, error_text)
        - Equal Division: Parts = সমান প্লট সংখ্যা (Value লাগে না)
        - By Shatak / By Sq.Ft: Value = প্রতিটি প্লটের ক্ষেত্রফল, Parts = ঐ মাপের কয়টি প্লট
          (শেষে বাকি জমি আলাদা একটি প্লট)। Parts ফাঁকা বা 0 হলে জমি শেষ না হওয়া পর্যন্ত কাটে।"""
        mode = self.spn_mode.text
        total = polygon_area(pts)
        parts_text = self.txt_parts.text.strip()
        try:
            parts = int(float(parts_text)) if parts_text else 0
        except ValueError:
            return 0, 1, 0, "Error: Please enter a valid number in the Parts box."
        if parts < 0:
            return 0, 1, 0, "Error: Parts cannot be negative."

        if mode == "Equal Division":
            if parts < 1:
                return 0, 1, 0, "Error: Please enter the number of parts (plots)."
            if parts > MAX_PLOTS:
                return 0, 1, 0, f"Error: Maximum {MAX_PLOTS} parts allowed (you entered {parts})."
            return 0, parts, 0, ""

        vtext = self.txt_part_val.text.strip()
        try:
            val = float(vtext)
        except ValueError:
            return 0, 1, 0, "Error: Please enter a valid number in the Value box."
        if val <= 0:
            return 0, 1, 0, "Error: Value must be greater than 0."
        target = val * SQFT_PER_SHATAK if mode == "By Shatak" else val
        unit = "Shatak" if mode == "By Shatak" else "sq.ft"
        fit = total / target
        shown = fit if mode == "By Shatak" else fit
        if parts:
            if parts * target > total + 0.5:
                return 0, 1, 0, (f"Error: {parts} plots of {val:g} {unit} need {parts * target:.2f} sq.ft, "
                                 f"but the land is {total:.2f} sq.ft. Maximum {int(fit)} plots possible.")
            if parts + 1 > MAX_PLOTS:
                return 0, 1, 0, f"Error: Maximum {MAX_PLOTS - 1} plots at a time (you entered {parts})."
            return target, 1, parts, ""
        if int(math.ceil(fit)) > MAX_PLOTS:
            need = total / MAX_PLOTS
            need_txt = f"{need / SQFT_PER_SHATAK:.2f} Shatak" if mode == "By Shatak" else f"{need:.0f} sq.ft"
            return 0, 1, 0, (f"Error: This would make {int(math.ceil(fit))} plots (max {MAX_PLOTS}). "
                             f"Enter at least {need_txt} or set Parts.")
        return target, 1, 0, ""

    def on_reset(self, instance):
        self.txt_s1.text = ""
        self.txt_s2.text = ""
        self.txt_s3.text = ""
        self.txt_s4.text = ""
        self.txt_diag.text = ""
        self.txt_part_val.text = "1"
        self.txt_parts.text = "1"
        self.last_partition_info = ""
        self.clear_adjust()
        self.lbl_area.text = "Total Area: 0.00 sq.ft (0.00 Shatak)"
        self.lbl_output.text = "Fields and map have been reset."
        self.lbl_ref_bounds.text = "Reference Diagonal Limits: --"
        self.map_widget.clear_canvas()

    def on_divide(self, instance):
        if not self.map_widget.pts or len(self.map_widget.pts) < 4:
            self.lbl_output.text = "Error: Please click 'Generate Land Map' first before dividing plot!"
            return

        vals = self.get_inputs()
        if not vals:
            return

        s1, s2, s3, s4, diag_val, diag_type = vals
        try:
            pts = calculate_quadrilateral(s1, s2, s3, s4, diag_val, diag_type)
            mode = self.spn_mode.text
            direction = self.spn_dir.text

            target_sqft, num_parts, max_cuts, err = self.read_division_params(pts)
            if err:
                self.lbl_output.text = err
                self.clear_adjust()
                return

            div_lines, part_area, is_vertical, partition_segments, sub_edge_segments = divide_polygon_directional(
                pts, num_parts, target_sqft, direction, max_cuts
            )

            if isinstance(is_vertical, str):
                self.lbl_output.text = is_vertical
                self.clear_adjust()
                return

            # ---- Adjustable mode (By Shatak / By Sq.Ft / Equal Division) ----
            if div_lines:
                equal = (mode == "Equal Division")
                targets = [k * part_area for k in range(1, len(div_lines) + 1)]
                adj = MultiCutAdjuster(pts, direction, targets)
                if adj.ok and adj.init_from_lines(div_lines, parallel=(self.spn_cutstyle.text == "Parallel to Start Edge")):
                    self.adj_ctx = {
                        "pts": pts, "sides": [s1, s2, s3, s4],
                        "diag_val": diag_val, "diag_type": diag_type,
                        "direction": direction, "total_area": polygon_area(pts),
                        "equal": equal, "part_area": part_area,
                    }
                    self.setup_adjust(adj)
                    self.render_adjusted()
                    return

            self.clear_adjust("Side adjustment is not available for this division.")

            self.map_widget.draw_map(
                pts, [s1, s2, s3, s4],
                diag_val=diag_val, diag_type=diag_type,
                div_lines=div_lines, part_area=part_area,
                is_vertical=is_vertical, partition_segments=partition_segments,
                sub_edge_segments=sub_edge_segments
            )

            shatak_val = part_area / SQFT_PER_SHATAK
            out_text = f"Direction: {direction}\n"
            out_text += f"Plot Area: {part_area:.2f} sq.ft ({shatak_val:.2f} Shatak)\n"
            out_text += f"Total Plots: {len(div_lines) + 1}"

            self.last_partition_info = out_text
            self.lbl_output.text = f"Partition Summary:\n{out_text}"
        except Exception as e:
            self.lbl_output.text = f"Divide Error: {str(e)}"

    # ==========================================
    # Adjacent-side adjustment (all plot areas fixed)
    # ==========================================
    def set_adjust_enabled(self, enabled):
        for w in (self.txt_adj_a, self.txt_adj_b, self.spn_cut, self.spn_pd_plot, self.spn_pd_type, self.spn_tag_mode,
                  self.spn_area_plot, self.txt_area_sqft, self.txt_area_shatak,
                  self.btn_sq_m, self.btn_sq_p, self.btn_sh_m, self.btn_sh_p,
                  self.btn_adj_a_minus, self.btn_adj_a_plus,
                  self.btn_adj_b_minus, self.btn_adj_b_plus):
            w.disabled = not enabled

    def clear_adjust(self, message=None):
        self.adjuster = None
        self.adj_ctx = {}
        self.adj_k = 0
        if self._adj_event is not None:
            self._adj_event.cancel()
            self._adj_event = None
        if self._area_event is not None:
            self._area_event.cancel()
            self._area_event = None
        self._adj_lock = True
        self.txt_adj_a.text = ""
        self.txt_adj_b.text = ""
        self.txt_area_sqft.text = ""
        self.txt_area_shatak.text = ""
        self.spn_area_plot.values = ("Plot 1",)
        self.spn_area_plot.text = "Plot 1"
        self.spn_cut.values = ("Plot 1",)
        self.spn_cut.text = "Plot 1"
        self.spn_pd_plot.values = ("Off",)
        self.spn_pd_plot.text = "Off"
        self.lbl_pd_info.text = "Divide a plot, then select a plot to see its diagonal."
        self._adj_lock = False
        self.lbl_adj_a_name.text = "-- --"
        self.lbl_adj_b_name.text = "-- --"
        self.lbl_adj_ref.text = message or self.DEFAULT_ADJ_MSG
        self.lbl_adj_ref.color = C_BLUE
        self.set_adjust_enabled(False)
        self.clear_plot_boxes()

    def clear_plot_boxes(self):
        if hasattr(self, "plot_boxes"):
            self.plot_boxes.clear_widgets()
            self.plot_boxes.height = 0

    def show_plot_boxes(self, plots):
        """প্রতিটি প্লট আলাদা রঙিন বক্সে (ডায়াগ্রামের রঙের সাথে মিল রেখে) দেখায়।"""
        self.plot_boxes.clear_widgets()
        for i, info in enumerate(plots):
            col = PLOT_COLORS[i % len(PLOT_COLORS)]
            dark = (col[0] * 0.55, col[1] * 0.55, col[2] * 0.55, 1)
            box = Card(bg=(col[0], col[1], col[2], 1), border=dark, radius=12,
                       orientation="vertical", padding=[dp(10), dp(5), dp(10), dp(5)],
                       spacing=dp(0), size_hint_y=None)
            box.bind(minimum_height=box.setter("height"))
            box.add_widget(auto_height_label(info["title"], color=dark, size=15, bold=True, min_h=22))
            box.add_widget(auto_height_label(info["line1"], color=C_TEXT, size=13, min_h=18))
            box.add_widget(auto_height_label(info["line2"], color=C_TEXT, size=13, min_h=18))
            if info.get("line3"):
                box.add_widget(auto_height_label(info["line3"], color=(0.75, 0.15, 0.02, 1),
                                                 size=13, bold=True, min_h=18))
            self.plot_boxes.add_widget(box)

    def setup_adjust(self, adj):
        self.adjuster = adj
        self.adj_k = 0
        self.set_adjust_enabled(True)
        c0 = adj.c0
        self.lbl_adj_a_name.text = f"{SIDE_NAME[c0.side_a_no]}\n(from P{c0.ia0 + 1})"
        self.lbl_adj_b_name.text = f"{SIDE_NAME[c0.side_b_no]}\n(from P{c0.ib0 + 1})"
        self._adj_lock = True
        self.spn_cut.values = tuple(f"Plot {i + 1}" for i in range(adj.n))
        self.spn_cut.text = "Plot 1"
        self.spn_area_plot.values = tuple(f"Plot {i + 1}" for i in range(adj.n + 1))
        self.spn_area_plot.text = "Plot 1"
        self.spn_pd_plot.values = ("Off", "All Plots") + tuple(f"Plot {i + 1}" for i in range(adj.n + 1))
        self.spn_pd_plot.text = "Off"
        self.lbl_pd_info.text = "Select a plot (or All Plots) to draw diagonals on the map."
        self._adj_lock = False
        self.refresh_adjust_fields()
        self.refresh_area_fields()

    def area_plot_index(self):
        try:
            return int(self.spn_area_plot.text.split()[1]) - 1
        except Exception:
            return 0

    def refresh_area_fields(self):
        adj = self.adjuster
        if adj is None:
            return
        i = min(self.area_plot_index(), adj.n)
        a = adj.plot_areas_now()[i]
        self._adj_lock = True
        self.txt_area_sqft.text = f"{a:.2f}"
        self.txt_area_shatak.text = f"{a / SQFT_PER_SHATAK:.2f}"
        self._adj_lock = False

    def on_area_plot_select(self, instance, text):
        if self._adj_lock or self.adjuster is None:
            return
        self.refresh_area_fields()

    def on_area_text(self, unit, instance, value):
        if self._adj_lock or self.adjuster is None:
            return
        if self._area_event is not None:
            self._area_event.cancel()
        self._area_event = Clock.schedule_once(partial(self.apply_area, unit), 0.8)

    def on_area_step(self, unit, sign, *args):
        adj = self.adjuster
        if adj is None:
            return
        if self._area_event is not None:
            self._area_event.cancel()
            self._area_event = None
        box = self.txt_area_sqft if unit == "sqft" else self.txt_area_shatak
        try:
            cur = float(box.text)
        except ValueError:
            return
        step = 10.0 if unit == "sqft" else 0.05
        self._adj_lock = True
        box.text = f"{max(0.0, cur + sign * step):.2f}"
        self._adj_lock = False
        self.apply_area(unit)

    def apply_area(self, unit, *args):
        adj = self.adjuster
        if adj is None:
            return
        i = min(self.area_plot_index(), adj.n)
        box = self.txt_area_sqft if unit == "sqft" else self.txt_area_shatak
        try:
            v = float(box.text.strip())
        except ValueError:
            self.lbl_output.text = "Area Error: Please enter a valid number."
            return
        new_area = v if unit == "sqft" else v * SQFT_PER_SHATAK
        ok, msg = adj.set_plot_area(i, new_area)
        if not ok:
            self.lbl_output.text = f"Area Error: {msg}"
            self.refresh_area_fields()
            return
        self.adj_ctx["custom"] = True
        self.refresh_adjust_fields()
        self.render_adjusted()

    def refresh_adjust_fields(self):
        adj = self.adjuster
        if adj is None:
            return
        k = self.adj_k
        x, y = adj.xy[k]
        pxa, pxb = self.prev_xy(k)
        self._adj_lock = True
        self.txt_adj_a.text = f"{x - pxa:.2f}"
        self.txt_adj_b.text = f"{y - pxb:.2f}"
        self._adj_lock = False
        self.update_ref_text()

    def prev_xy(self, k):
        """আগের প্লটের শেষ (cumulative) অবস্থান; Plot 1 এর জন্য (0, 0)।"""
        if k > 0 and self.adjuster is not None:
            return self.adjuster.xy[k - 1][0], self.adjuster.xy[k - 1][1]
        return 0.0, 0.0

    def update_ref_text(self):
        adj = self.adjuster
        if adj is None:
            return
        k = self.adj_k
        c0 = adj.c0
        pxa, pxb = self.prev_xy(k)
        a_lo, a_hi = adj.bounds(k, "a")
        b_lo, b_hi = adj.bounds(k, "b")
        a_lo, a_hi, b_lo, b_hi = a_lo - pxa, a_hi - pxa, b_lo - pxb, b_hi - pxb
        pa = self.adj_ctx["part_area"]
        if self.adj_ctx.get("custom"):
            ar = adj.plot_areas_now()
            head = (f"Plot {k + 1}: {ar[k]:.2f} sq.ft ({ar[k] / SQFT_PER_SHATAK:.2f} Shatak) | "
                    f"Plot {k + 2}: {ar[k + 1]:.2f} sq.ft ({ar[k + 1] / SQFT_PER_SHATAK:.2f} Shatak) "
                    f"- sides of Plot {k + 1}")
        elif self.adj_ctx["equal"]:
            head = (f"Boundary between Plot {k + 1} and Plot {k + 2}: all {adj.n + 1} plots "
                    f"stay equal ({pa:.2f} sq.ft each)")
        else:
            head = (f"Plot {k + 1} fixed area: {pa:.2f} sq.ft ({pa / SQFT_PER_SHATAK:.2f} Shatak) "
                    f"- adjusting Plot {k + 1} sides (boundary with Plot {k + 2})")
        self.lbl_adj_ref.text = (
            f"{head}\n"
            f"Plot {k + 1} {SIDE_NAME[c0.side_a_no]} allowed: {a_lo:.2f} to {a_hi:.2f} ft\n"
            f"Plot {k + 1} {SIDE_NAME[c0.side_b_no]} allowed: {b_lo:.2f} to {b_hi:.2f} ft"
        )
        self.lbl_adj_ref.color = (0.0, 0.5, 0.2, 1)

    def on_cut_select(self, instance, text):
        if self._adj_lock or self.adjuster is None:
            return
        try:
            k = int(text.split()[1]) - 1
        except Exception:
            return
        if 0 <= k < self.adjuster.n:
            self.adj_k = k
            self.refresh_adjust_fields()

    def on_pd_change(self, instance, value):
        if self._adj_lock or self.adjuster is None:
            return
        self.render_adjusted()

    @staticmethod
    def plot_corner_map(poly, vertical):
        """প্লটের চার কোণাকে NW/NE/SW/SE নাম দেয় (poly = [A1, A2, B2, B1])।"""
        pa0, pa1, pb1, pb0 = poly
        if vertical:
            na = sorted([pa0, pa1], key=lambda p: p[0])
            nb = sorted([pb0, pb1], key=lambda p: p[0])
            return {"NW": na[0], "NE": na[1], "SW": nb[0], "SE": nb[1]}
        wa = sorted([pa0, pa1], key=lambda p: -p[1])
        eb = sorted([pb0, pb1], key=lambda p: -p[1])
        return {"NW": wa[0], "SW": wa[1], "NE": eb[0], "SE": eb[1]}

    def on_adj_text(self, which, instance, value):
        if self._adj_lock or self.adjuster is None:
            return
        if self._adj_event is not None:
            self._adj_event.cancel()
        self._adj_event = Clock.schedule_once(partial(self.apply_adjust, which), 0.6)

    def on_adj_step(self, which, delta, *args):
        adj = self.adjuster
        if adj is None:
            return
        if self._adj_event is not None:
            self._adj_event.cancel()
            self._adj_event = None
        box = self.txt_adj_a if which == "a" else self.txt_adj_b
        off = self.prev_xy(self.adj_k)[0 if which == "a" else 1]
        lo, hi = adj.bounds(self.adj_k, which)
        lo, hi = lo - off, hi - off
        try:
            cur = float(box.text)
        except ValueError:
            cur = lo
        new_val = min(hi, max(lo, cur + delta))
        self._adj_lock = True
        box.text = f"{new_val:.2f}"
        self._adj_lock = False
        self.apply_adjust(which)

    def apply_adjust(self, which, *args):
        adj = self.adjuster
        if adj is None:
            return
        k = self.adj_k
        c0 = adj.c0
        src = self.txt_adj_a if which == "a" else self.txt_adj_b
        dst = self.txt_adj_b if which == "a" else self.txt_adj_a
        side_no = SIDE_NAME[c0.side_a_no if which == "a" else c0.side_b_no]
        pxa, pxb = self.prev_xy(k)
        off_src, off_dst = (pxa, pxb) if which == "a" else (pxb, pxa)
        lo, hi = adj.bounds(k, which)
        lo, hi = lo - off_src, hi - off_src

        try:
            v = float(src.text.strip())
        except ValueError:
            self.lbl_output.text = f"Adjust Error: Please enter a valid number for {side_no}."
            return

        if v < lo - 0.005 or v > hi + 0.005:
            self.lbl_output.text = (
                f"Adjust Error: {side_no} must be between {lo:.2f} and {hi:.2f} ft "
                f"to keep the plot area fixed."
            )
            return

        v = min(hi, max(lo, v)) + off_src          # cumulative মান
        other = adj.cuts[k].solve(which, v)
        if other is None:
            self.lbl_output.text = f"Adjust Error: {side_no} = {v - off_src:.2f} ft is not possible for this area."
            return

        self._adj_lock = True
        dst.text = f"{other - off_dst:.2f}"
        self._adj_lock = False

        adj.xy[k] = [v, other] if which == "a" else [other, v]
        self.update_ref_text()
        self.render_adjusted()

    def render_adjusted(self):
        adj = self.adjuster
        ctx = self.adj_ctx
        if adj is None or not ctx:
            return
        g = adj.geometry()
        c0 = adj.c0

        # ---- কর্ণ (নির্বাচিত প্লট / All Plots) + প্লট নম্বর ও শতকের ট্যাগ ----
        plot_tags = []
        diag_notes = []
        sel = self.spn_pd_plot.text
        tag_mode = self.spn_tag_mode.text
        kind = self.spn_pd_type.text
        combos = [("NW", "SE"), ("NE", "SW")] if kind == "Both" else [tuple(kind.split("-"))]
        n_polys = len(g["plot_polys"])
        if sel == "All Plots":
            chosen = set(range(n_polys))
        elif sel.startswith("Plot"):
            try:
                chosen = {int(sel.split()[1]) - 1}
            except Exception:
                chosen = set()
        else:
            chosen = set()
        for pi in range(n_polys):
            if pi not in chosen and tag_mode == "Off":
                continue
            try:
                cm = self.plot_corner_map(g["plot_polys"][pi], adj.is_vertical)
                anchor = (cm[combos[0][0]], cm[combos[0][1]])
                diags = []
                if pi in chosen:
                    for u_, v_ in combos:
                        p_, q_ = cm[u_], cm[v_]
                        diags.append((p_, q_))
                        diag_notes.append((pi, f"{u_}-{v_}", dist(p_, q_)))
                plot_tags.append({"pi": pi, "anchor": anchor, "diags": diags})
            except Exception:
                pass
        if diag_notes:
            self.lbl_pd_info.text = "\n".join(
                f"Plot {pi + 1} diagonal {nm}: {ln:.2f} ft" for pi, nm, ln in diag_notes)
        elif sel.startswith("Plot") or sel == "All Plots":
            self.lbl_pd_info.text = "Diagonal not available for this plot."
        else:
            self.lbl_pd_info.text = "Select a plot (or All Plots) to draw diagonals on the map."

        self.map_widget.draw_map(
            ctx["pts"], ctx["sides"],
            diag_val=ctx["diag_val"], diag_type=ctx["diag_type"],
            div_lines=[], part_area=ctx["part_area"],
            is_vertical=adj.is_vertical,
            partition_segments=g["partition_segments"],
            sub_edge_segments=g["sub_edge_segments"],
            plot_polys=g["plot_polys"],
            plot_tags=plot_tags, plot_areas=g["plot_areas"], tag_mode=tag_mode,
        )

        pa = ctx["part_area"]
        sh = SQFT_PER_SHATAK
        a_no, b_no = c0.side_a_no, c0.side_b_no
        total_plots = adj.n + 1

        # ---- প্রতিটি প্লটের তথ্য ----
        plots = []
        pdf_lines = [f"Direction: {ctx['direction']}", f"Total Plots: {total_plots}"]
        for i, poly in enumerate(g["plot_polys"]):
            area_i = g["plot_areas"][i]
            side_a = dist(poly[0], poly[1])      # A বাহুর অংশ
            end_ln = dist(poly[1], poly[2])      # পরের রেখা / শেষ বাহু
            side_b = dist(poly[2], poly[3])      # B বাহুর অংশ
            start_ln = dist(poly[3], poly[0])    # আগের রেখা / শুরুর বাহু
            start_name = "Start Side" if i == 0 else f"Line with Plot {i}"
            end_name = "Far Side" if i == total_plots - 1 else f"Line with Plot {i + 2}"
            tag = " (Remaining)" if (not ctx["equal"] and not ctx.get("custom") and i == total_plots - 1) else ""
            plots.append({
                "title": f"Plot {i + 1}{tag}  -  {area_i:.2f} sq.ft ({area_i / sh:.2f} Shatak)",
                "line1": f"{SIDE_NAME[a_no]}: {side_a:.2f} ft   |   {SIDE_NAME[b_no]}: {side_b:.2f} ft",
                "line2": f"{start_name}: {start_ln:.2f} ft   |   {end_name}: {end_ln:.2f} ft",
            })
            notes_i = [f"{nm}: {ln:.2f} ft" for pi, nm, ln in diag_notes if pi == i]
            if notes_i:
                plots[-1]["line3"] = "Diagonal " + "   |   ".join(notes_i)
            pdf_lines.append(
                f"Plot {i + 1}{tag}: {area_i:.2f} sq.ft ({area_i / sh:.2f} Shatak) | "
                f"{SIDE_NAME[a_no]}: {side_a:.2f} ft | {SIDE_NAME[b_no]}: {side_b:.2f} ft"
            )
            for pi, nm, ln in diag_notes:
                if pi == i:
                    pdf_lines.append(f"   Plot {i + 1} diagonal {nm}: {ln:.2f} ft")

        head = f"Direction: {ctx['direction']}\nTotal Plots: {total_plots}"
        if ctx["equal"] and not ctx.get("custom"):
            head += f"  (each {pa:.2f} sq.ft | {pa / sh:.2f} Shatak)"
        self.lbl_output.text = head
        self.last_partition_info = "\n".join(pdf_lines)
        self.show_plot_boxes(plots)
        self.refresh_area_fields()

    # ==========================================
    # Save dialog / exports
    # ==========================================
    def open_save_dialog(self, default_filename, on_save_callback):
        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))

        if platform == 'android':
            start_path = '/storage/emulated/0'
            root_path = '/storage/emulated/0'
            if not os.path.exists(start_path):
                start_path = os.path.expanduser('~')
                root_path = '/'
        else:
            start_path = os.path.expanduser('~')
            if os.path.exists(os.path.join(start_path, 'Downloads')):
                start_path = os.path.join(start_path, 'Downloads')
            root_path = '/'

        file_chooser = FileChooserListView(
            path=start_path,
            rootpath=root_path,
            dirselect=True,
            size_hint=(1, 0.75)
        )
        content.add_widget(file_chooser)

        fn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44), spacing=dp(5))
        fn_layout.add_widget(Label(text="File Name:", size_hint_x=0.3, color=(1, 1, 1, 1), bold=True))
        txt_filename = TextInput(text=default_filename, multiline=False, size_hint_x=0.7)
        fn_layout.add_widget(txt_filename)
        content.add_widget(fn_layout)

        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(46), spacing=dp(10))
        btn_cancel = RoundedButton(text="Cancel", bg=C_RED)
        btn_save = RoundedButton(text="Save", bg=C_GREEN)

        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_save)
        content.add_widget(btn_layout)

        popup = Popup(
            title="Choose Directory & Name File",
            content=content,
            size_hint=(0.95, 0.95),
            auto_dismiss=False
        )

        def save_action(instance):
            selected_dir = file_chooser.path
            if file_chooser.selection and os.path.isdir(file_chooser.selection[0]):
                selected_dir = file_chooser.selection[0]

            filename = txt_filename.text.strip()
            if filename:
                full_path = os.path.join(selected_dir, filename)
                popup.dismiss()
                on_save_callback(full_path)
            else:
                self.lbl_output.text = "Error: Please enter a valid file name."

        btn_save.bind(on_press=save_action)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()

    def on_export_cad(self, instance):
        if not self.map_widget.pts or len(self.map_widget.pts) < 4:
            self.lbl_output.text = "Error: Please click 'Generate Land Map' first before exporting CAD!"
            return

        vals = self.get_inputs()
        if not vals:
            return

        def do_cad_export(full_path):
            s1, s2, s3, s4, diag_val, diag_type = vals
            try:
                pts = calculate_quadrilateral(s1, s2, s3, s4, diag_val, diag_type)
                direction = self.spn_dir.text
                mode = self.spn_mode.text

                if self.adjuster is not None:
                    # স্ক্রিনে যে (অ্যাডজাস্টকৃত) বন্টন রেখাগুলো দেখা যাচ্ছে সেগুলোই এক্সপোর্ট হবে
                    partition_segments = list(self.map_widget.partition_segments)
                else:
                    try:
                        target_sqft, num_parts, max_cuts, err = self.read_division_params(pts)
                        if err:
                            raise ValueError(err)
                        _, _, _, partition_segments, _ = divide_polygon_directional(
                            pts, num_parts, target_sqft, direction, max_cuts)
                    except Exception:
                        partition_segments = []

                filePath = export_to_dxf(pts, partition_segments, full_path)
                self.lbl_output.text = f"CAD Export Successful!\nSaved File Path:\n{filePath}"
            except Exception as e:
                self.lbl_output.text = f"Export Error: {str(e)}"

        self.open_save_dialog("land_map.dxf", do_cad_export)

    def on_export_pdf(self, instance):
        if not self.map_widget.pts or len(self.map_widget.pts) < 4:
            self.lbl_output.text = "Error: Please click 'Generate Land Map' first before exporting PDF!"
            return

        vals = self.get_inputs()
        if not vals:
            return

        def do_pdf_export(full_path):
            s1, s2, s3, s4, diag_val, diag_type = vals
            try:
                pts = calculate_quadrilateral(s1, s2, s3, s4, diag_val, diag_type)

                pdf_path = export_to_pdf(
                    pts=pts,
                    sides=[s1, s2, s3, s4],
                    diag_val=diag_val,
                    diag_type=diag_type,
                    full_filepath=full_path,
                    part_summary_text=self.last_partition_info,
                    partition_segments=self.map_widget.partition_segments,
                    sub_edge_segments=self.map_widget.sub_edge_segments,
                    is_vertical=self.map_widget.is_vertical,
                    plot_polys=self.map_widget.plot_polys,
                    plot_tags=self.map_widget.plot_tags,
                    plot_areas=self.map_widget.plot_areas,
                    tag_mode=self.map_widget.tag_mode,
                )
                self.lbl_output.text = f"PDF Export Successful!\nSaved PDF File Path:\n{pdf_path}"
            except Exception as e:
                self.lbl_output.text = f"PDF Export Error: {str(e)}"

        self.open_save_dialog("land_report.pdf", do_pdf_export)


# ==========================================
# 5. Program Entry Point
# ==========================================
if __name__ == "__main__":
    SSRKLandApp().run()
