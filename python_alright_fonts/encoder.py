import freetype
import struct
from .util import Bounds, Glyph, Point
import shapely

DEBUG = True

END_OF_TEXT = 0x01ff


def load_glyph(face, codepoint, scale_factor, quality=30, precision=2, target_bounds=None, offset=None, include_bounding_box=False):
  # glyph doesn't exist in face
  if face.get_char_index(codepoint) == 0:
    return None

  # glyph isn't printable
  #if not chr(codepoint).isprintable():
  #  print("Glyph not printable")
  #  return None

  # load the glyph
  face.load_char(codepoint, freetype.FT_LOAD_PEDANTIC)

  glyph = Glyph()
  glyph.codepoint = codepoint # utf-8 codepoint or ascii character code

  source_bounds = Bounds(face.glyph.outline.get_bbox())

  target_bounds = target_bounds or Bounds(255, 255)
  offset = offset or Point(0, 0)

  scale_x = source_bounds.width / target_bounds.width
  scale_y = source_bounds.height / target_bounds.height

  if codepoint >= END_OF_TEXT:
    scale_factor = max(scale_x, scale_y)

  print(f"> target bounds: {target_bounds.width:.2f} x {target_bounds.height:.2f}")
  print(f"> source bounds: {source_bounds.width:.2f} x {source_bounds.height:.2f}")
  print(f"> scale: {scale_x:.6f} x {scale_y:.6f}")
  print(f"> scale factor: {scale_factor:.6f}")

  #print(f"w: {scaled_width}, h: {scaled_height}")
  #offset_x = ((target_width - scaled_width) / 2) - tbxMin
  #offset_y = ((target_height - scaled_height) / 2) - tbyMin


  # extract glyph contours
  outline = face.glyph.outline
  glyph.contours = []
  #start = 0

  def move_to(p, ctx):
    # Move to always starts a new contour
    ctx.contours.append([[p.x, p.y]])

  def line_to(a, ctx):
    ctx.contours[-1].append([a.x, a.y])

  def quadratic_bezier(t, src, c1, dst):
    return [
      (1 - t) * (1 - t) * src.x + 2 * (1 - t) * t * c1.x + t * t * dst.x,
      (1 - t) * (1 - t) * src.y + 2 * (1 - t) * t * c1.y + t * t * dst.y
    ]

  def conic_to(c1, dst, ctx):
    # Draw a quadratic bezier from the previous point to dst, with control c1

    # Get the source point (last point in this contour)
    src = Point(ctx.contours[-1][-1][0], ctx.contours[-1][-1][1])
    c1 = Point(c1.x, c1.y)
    dst = Point(dst.x, dst.y)

    distance = int(src.distance(c1) + c1.distance(dst))
    #if DEBUG: print(f"Decomposing conic curve with distance: {distance}")

    # simplify_coords_vwp will discard overlapping/proximal/redundant coords
    for i in range(distance):
      ctx.contours[-1].append(quadratic_bezier(i / distance, src, c1, dst))

  def cubic_bezier(t, src, c1, c2, dst):
    return [
      ((1 - t) ** 3) * src.x + 3 * ((1 - t) ** 2) * t * c1.x + 3 * (1 - t) * (t ** 2) * c2.x + (t ** 3) * dst.x,
      ((1 - t) ** 3) * src.y + 3 * ((1 - t) ** 2) * t * c1.y + 3 * (1 - t) * (t ** 2) * c2.y + (t ** 3) * dst.y
    ]

  def cubic_to(c1, c2, dst, ctx):
    # Draw a cubic bezier from the previous point to dst, with controls c1 and c2

    # Get the source point (last point in this contour)
    src = Point(ctx.contours[-1][-1][0], ctx.contours[-1][-1][1])
    c1 = Point(c1.x, c1.y)
    c2 = Point(c2.x, c2.y)
    dst = Point(dst.x, dst.y)

    distance = src.distance(c1) + c1.distance(c2) + c2.distance(dst)
    #if DEBUG: print(f"Decomposing cubic curve with distance: {distance}")

    # simplify_coords_vwp will discard overlapping/proximal/redundant coords
    for i in range(distance):
      ctx.contours[-1].append(cubic_bezier(i / distance, src, c1, c2, dst))

  outline.decompose(glyph, move_to=move_to, line_to=line_to, conic_to=conic_to, cubic_to=cubic_to)

  # Skip non-printable, empty chars. We want to preserve space.
  if not glyph.contours and not chr(codepoint).isprintable():
     return None

  # SHAPELY
  if glyph.contours:
      polygons = shapely.polygons([shapely.LinearRing(contour) for contour in glyph.contours if len(contour) > 3])
      polygons = [poly.buffer(0) for poly in polygons]

      # Collapse multipolygons
      for i in range(len(polygons)):
          if geoms := getattr(polygons[i], "geoms", None):
              polygons += geoms
              polygons[i] = None

      polygons = [polygon for polygon in polygons if polygon is not None]

      def merge_partial_overlaps(polygons):
          def any_overlaps(polygons):
              for a in polygons:
                  for b in polygons:
                      if shapely.overlaps(a, b):
                          return True
              return False

          def do_merge(polygons):
              for i_a in range(len(polygons)):
                  for i_b in range(len(polygons)):
                      a = polygons[i_a]
                      b = polygons[i_b]
                      if a and b and shapely.overlaps(a, b):
                          polygons[i_a] = shapely.union(a, b)
                          polygons[i_b] = None
              return [polygon for polygon in polygons if polygon is not None]

          # Merge until there are no (partially) overlapping polygons
          while any_overlaps(polygons):
              polygons = do_merge(polygons)

          return polygons

      polygons = merge_partial_overlaps(polygons)

      valid = shapely.is_valid(polygons)
      for i in range(len(polygons)):
          if not valid[i]:
              polygons[i] = polygons[i].buffer(0)

      # Resolve the polygons into inner/outer enclosed rings
      polygons = shapely.polygons(shapely.get_rings(polygons))

      polygons = shapely.coverage_simplify(polygons, tolerance=quality // 2)

      p_scale = Point(scale_factor, -scale_factor)
      glyph.contours = [[Point(x, y) / p_scale for x, y in shapely.get_coordinates(poly)] for poly in polygons]

  if codepoint >= END_OF_TEXT:
    # Get the scaled bounding box
    actual_bounds = Bounds(65535, 65535, -65535, -65535)

    for c in glyph.contours:
        for point in c:
            actual_bounds.update(point)

    print(f"> scaled bounds: {actual_bounds.x:.2f} {actual_bounds.y:.2f} {actual_bounds.x2:.2f} {actual_bounds.y2:.2f}")

    # Cancel out any offset to align to the top left
    offset += Point(-actual_bounds.x, -actual_bounds.y)

    # Calculate an offset based on the bounding box and center the result
    offset.x += (target_bounds.width - actual_bounds.width) / 2
    offset.y += (target_bounds.height - actual_bounds.height) / 2

    # Move to the center of our target bounds
    offset.x -= target_bounds.width / 2
    offset.y -= target_bounds.height / 2

    print(f"> offset: {offset.x:.2f}:{offset.y:.2f}")

    for c in glyph.contours:
        for p in c:
            p.set(round(p + offset, precision))

  if include_bounding_box:
      glyph.contours.insert(0, target_bounds.contour)

  # A contour *must* have at least three points. Discard any invalid contours.
  old_size = len(glyph.contours)
  glyph.contours = [contour for contour in glyph.contours if len(contour) > 2]

  print(f"> result: {len(glyph.contours)} contours with {sum(len(c) for c in glyph.contours)} points")

  if old_size > len(glyph.contours):
      print(f"> result: {old_size - len(glyph.contours)} invalid contour(s) skipped!")

  if codepoint >= END_OF_TEXT:
    glyph.bbox_x = int(target_bounds.x)
    glyph.bbox_y = int(target_bounds.y)
    glyph.bbox_w = int(target_bounds.width)
    glyph.bbox_h = int(target_bounds.height)
    glyph.advance = 255
  else:
    bbox = face.glyph.outline.get_bbox()
    glyph.bbox_x = int( bbox.xMin / scale_factor)
    glyph.bbox_y = int( bbox.yMin / scale_factor)
    glyph.bbox_w = int((bbox.xMax - bbox.xMin) / scale_factor)
    glyph.bbox_h = int((bbox.yMax - bbox.yMin) / scale_factor)
    glyph.advance = round(face.glyph.metrics.horiAdvance / scale_factor)

  return glyph

class Encoder():
  def __init__(self, font, icon_font, quality = 30):
    self.face = freetype.Face(font)
    self.icon_face = None if icon_font is None else freetype.Face(icon_font)

    print(self.face.get_format())
    self.bbox_l = self.face.bbox.xMin
    self.bbox_t = self.face.bbox.yMin
    self.bbox_r = self.face.bbox.xMax
    self.bbox_b = self.face.bbox.yMax
    self.glyphs = {}
    self.packed_glyph_contours = {}

    self.quality = quality

    normalising_scale_factor = max(
      abs(self.bbox_l), abs(self.bbox_t),
      abs(self.bbox_r), abs(self.bbox_b))

    self.scale_factor = normalising_scale_factor / 127

    self.bbox_l /= self.scale_factor
    self.bbox_t /= self.scale_factor
    self.bbox_r /= self.scale_factor
    self.bbox_b /= self.scale_factor

  def __del__(self):
    # consume rogue error when destroying the face object
    try:
      del self.face
      del self.icon_font
    except AttributeError:
      pass

  def get_glyph(self, codepoint):
    if codepoint not in self.glyphs:
      glyph = load_glyph(self.face if codepoint <= END_OF_TEXT or self.icon_face is None else self.icon_face, codepoint, self.scale_factor, self.quality)
      if not glyph:
        return None
      self.glyphs[codepoint] = glyph
    return self.glyphs[codepoint]

  def get_packed_glyph(self, glyph):
    pack_format = ">HbbBBBB"
    return struct.pack(
      pack_format,
      glyph.codepoint,
      glyph.bbox_x,
      glyph.bbox_y,
      glyph.bbox_w,
      glyph.bbox_h,
      glyph.advance,
      len(glyph.contours)
    )

  def get_packed_glyph_paths(self, glyph):
    result = bytes()
    for contour in glyph.contours:
      if len(contour) > 65535:
        raise RuntimeError(f"Fatal: Contour too big! {len(contour)}")
      result += struct.pack(">H", len(contour))
    return result

  def get_packed_glyph_path_points(self, glyph):
    result = bytes()
    for contour in glyph.contours:
      for point in contour:
        result += struct.pack(">bb", int(point.x), int(point.y))
    return result

  def total_path_count(self):
    total = 0
    for glyph in self.glyphs:
      total += len(self.glyphs[glyph].contours)
    return total

  def total_point_count(self):
    total = 0
    for glyph in self.glyphs:
      for contour in self.glyphs[glyph].contours:
        total += len(contour)
    return total

