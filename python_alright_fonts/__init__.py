import math
import freetype


class Point:
    def __init__(self, *args):
        if isinstance(args[0], (tuple, list)):
            self.x = args[0][0]
            self.y = args[0][1]
        else:
            self.x = args[0]
            self.y = args[1]

    def __iter__(self):
        return iter((self.x, self.y))

    def set(self, other):
        self.x = other.x
        self.y = other.y

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)

    def __div__(self, other):
        if isinstance(other, Point):
            return Point(self.x / other.x, self.y / other.y)
        if isinstance(other, (int, float)):
            return Point(self.x / other, self.y / other)
        raise ValueError

    __truediv__ = __div__

    def __mul__(self, other):
        if isinstance(other, Point):
            return Point(self.x * other.x, self.y * other.y)
        if isinstance(other, (int, float)):
            return Point(self.x * other, self.y * other)
        raise ValueError

    __rmul__ = __mul__

    def __round__(self, dp=0):
        return Point(round(self.x, dp), round(self.y, dp))

    def distance(self, other):
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return math.sqrt(dx * dx + dy * dy)

    def __repr__(self):
        return "({}, {})".format(self.x, self.y)

    @staticmethod
    def parse_arg(arg):
        return Point(*(int(c) for c in arg.split("x")))


class Bounds:
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], freetype.BBox):
            bb = args[0]
            self.x = bb.xMin
            self.x2 = bb.xMax
            self.y = bb.yMin
            self.y2 = bb.yMax
        elif len(args) == 2:
            width, height = args
            self.x = -width / 2
            self.y = -height / 2
            self.x2 = width / 2
            self.y2 = height / 2
        else:
            self.x, self.y, self.x2, self.y2 = args

    def update(self, point):
        self.x = min(self.x, point.x)
        self.y = min(self.y, point.y)
        self.x2 = max(self.x2, point.x)
        self.y2 = max(self.y2, point.y)

    @property
    def width(self):
        return self.x2 - self.x

    @property
    def height(self):
        return self.y2 - self.y

    @property
    def contour(self):
        return [
            Point(self.x, self.y),
            Point(self.x2, self.y),
            Point(self.x2, self.y2),
            Point(self.x, self.y2),
        ]

    @staticmethod
    def parse_arg(arg):
        return Bounds(*(int(c) for c in arg.split("x")))


class Glyph():
  def __init__(self):
    self.codepoint = None
    self.advance = None
    self.bbox_x = None
    self.bbox_y = None
    self.bbox_w = None
    self.bbox_h = None
    self.contours = []
  
  def __repr__(self):
    return "{} ({},{}: {}x{}) [{}]".format(self.codepoint, self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h, self.advance)

class Face():
  def __init__(self):
    self.glyphs = {}
    pass

  def get_glyph(self, codepoint):
    if codepoint not in self.glyphs:
      return None

    return self.glyphs[codepoint]    

from python_alright_fonts.encoder import Encoder
from python_alright_fonts.loader import load_font
