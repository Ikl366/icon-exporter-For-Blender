bl_info = {
    "name": "ICO Exporter",
    "author": "the secret >:D",
    "version": (0, 1, 2),
    "blender": (4, 4, 0),
    "location": "Image Editor > Image > Export as ICO  /  Properties > Output > Export as ICO",
    "description": "Export images in .ico format with multiple size support.",
    "category": "Import-Export",
    "doc_url": "https://github.com/Ikl366/icon-exporter-For-Blender",
}

import bpy
import os
import struct
import zlib
import tempfile
from bpy.props import (
    StringProperty, EnumProperty, BoolProperty,
)
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ExportHelper


def get_pixels_from_image(image: bpy.types.Image):
    if image.type not in {"RENDER_RESULT", "COMPOSITING"}:
        w, h = image.size
        if w == 0 or h == 0:
            raise RuntimeError(f"Image «{image.name}» is zero in size.")
        return list(image.pixels), w, h

    w, h = image.size
    if w == 0 or h == 0:
        raise RuntimeError(
            "Render Result is empty. Make sure the render is completed (F12) and "
            "the image appears in the Image Editor."
        )

    tmp_path = os.path.join(tempfile.gettempdir(), "_ico_export_tmp.png")

    scene = bpy.context.scene
    orig_path   = scene.render.filepath
    orig_format = scene.render.image_settings.file_format
    orig_color  = scene.render.image_settings.color_mode

    try:
        scene.render.filepath = tmp_path
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode  = "RGBA"
        image.save_render(tmp_path, scene=scene)
    finally:
        scene.render.filepath = orig_path
        scene.render.image_settings.file_format = orig_format
        scene.render.image_settings.color_mode  = orig_color

    if not os.path.exists(tmp_path):
        raise RuntimeError("Unable to save temporary PNG from Render Result.")

    tmp_img = bpy.data.images.load(tmp_path, check_existing=False)
    try:
        tw, th = tmp_img.size
        pixels = list(tmp_img.pixels)
    finally:
        bpy.data.images.remove(tmp_img)
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return pixels, tw, th


def _pack_png(width: int, height: int, pixels_flat: list) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    raw_rows = bytearray()
    stride = width * 4
    for y in range(height):
        raw_rows.append(0)
        row_start = (height - 1 - y) * stride
        for i in range(width * 4):
            v = pixels_flat[row_start + i]
            raw_rows.append(max(0, min(255, int(round(v * 255)))))

    compressed = zlib.compress(bytes(raw_rows), 9)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr_data)
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    return png


def _resize_pixels(src_pixels: list, src_w: int, src_h: int,
                   dst_w: int, dst_h: int) -> list:
    out = []
    for dy in range(dst_h):
        fy = dy * (src_h - 1) / max(dst_h - 1, 1)
        y0 = int(fy)
        y1 = min(y0 + 1, src_h - 1)
        vy = fy - y0
        for dx in range(dst_w):
            fx = dx * (src_w - 1) / max(dst_w - 1, 1)
            x0 = int(fx)
            x1 = min(x0 + 1, src_w - 1)
            vx = fx - x0
            for c in range(4):
                def p(x, y, c=c): return src_pixels[(y * src_w + x) * 4 + c]
                val = (p(x0, y0) * (1 - vx) * (1 - vy) +
                       p(x1, y0) *      vx  * (1 - vy) +
                       p(x0, y1) * (1 - vx) *      vy  +
                       p(x1, y1) *      vx  *      vy)
                out.append(val)
    return out


def build_ico_single(src_pixels: list, src_w: int, src_h: int, sz: int) -> bytes:
    if sz == src_w and sz == src_h:
        px = src_pixels
    else:
        px = _resize_pixels(src_pixels, src_w, src_h, sz, sz)
    png_data = _pack_png(sz, sz, px)

    ico = bytearray()
    ico += struct.pack("<HHH", 0, 1, 1)
    w = 0 if sz >= 256 else sz
    h = 0 if sz >= 256 else sz
    ico += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_data), 6 + 16)
    ico += png_data
    return bytes(ico)


class IcoExportProperties(bpy.types.PropertyGroup):
    size_16:  BoolProperty(name="16×16",   default=True)
    size_24:  BoolProperty(name="24×24",   default=False)
    size_32:  BoolProperty(name="32×32",   default=True)
    size_48:  BoolProperty(name="48×48",   default=True)
    size_64:  BoolProperty(name="64×64",   default=False)
    size_128: BoolProperty(name="128×128", default=False)
    size_256: BoolProperty(name="256×256", default=True)

    Source: EnumProperty(
        name="Source",
        items=[
            ("ACTIVE", "Active Image",  "Image Editor / active image"),
            ("RENDER", "Render Result", "Use the render buffer"),
        ],
        default="ACTIVE",
    )


class IMAGE_OT_export_ico(Operator, ExportHelper):
    bl_idname = "image.export_ico"
    bl_label  = "Export as ICO"
    bl_description = "Save image in .ico format (Windows Icon)"
    bl_options = {"REGISTER"}

    filename_ext = ".ico"
    filter_glob: StringProperty(default="*.ico", options={"HIDDEN"})

    size_16:  BoolProperty(name="16×16",   default=True)
    size_24:  BoolProperty(name="24×24",   default=False)
    size_32:  BoolProperty(name="32×32",   default=True)
    size_48:  BoolProperty(name="48×48",   default=True)
    size_64:  BoolProperty(name="64×64",   default=False)
    size_128: BoolProperty(name="128×128", default=False)
    size_256: BoolProperty(name="256×256", default=True)

    Source: EnumProperty(
        name="Source",
        items=[
            ("ACTIVE", "Active Image",  ""),
            ("RENDER", "Render Result", ""),
        ],
        default="ACTIVE",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Source:")
        layout.prop(self, "Source", text="")
        layout.separator()
        layout.label(text="Icon sizes:")
        col = layout.column(align=True)
        for attr in ("size_16", "size_24", "size_32", "size_48",
                     "size_64", "size_128", "size_256"):
            col.prop(self, attr)

    def execute(self, context):
        sizes = []
        for attr, sz in [("size_16", 16), ("size_24", 24), ("size_32", 32),
                         ("size_48", 48), ("size_64", 64), ("size_128", 128),
                         ("size_256", 256)]:
            if getattr(self, attr):
                sizes.append(sz)
        if not sizes:
            sizes = [32]

        image = None
        if self.Source == "RENDER":
            image = bpy.data.images.get("Render Result")
            if image is None:
                self.report({"ERROR"}, "No Render Result. Run the renderer first (F12).")
                return {"CANCELLED"}
        else:
            for area in context.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    image = area.spaces.active.image
                    break
            if image is None:
                for img in bpy.data.images:
                    if img.type not in {"RENDER_RESULT", "COMPOSITING"}:
                        image = img
                        break

        if image is None:
            self.report({"ERROR"}, "Image not found. Open the Image Editor with an image.")
            return {"CANCELLED"}

        try:
            src_pixels, src_w, src_h = get_pixels_from_image(image)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        base = os.path.splitext(self.filepath)[0]
        if base.lower().endswith(".ico"):
            base = base[:-4]

        saved = []
        errors = []
        for sz in sorted(sizes):
            try:
                ico_bytes = build_ico_single(src_pixels, src_w, src_h, sz)
            except Exception as e:
                errors.append(f"{sz}px: {e}")
                continue

            out_path = f"{base}_{sz}x{sz}.ico"
            try:
                with open(out_path, "wb") as f:
                    f.write(ico_bytes)
                saved.append(sz)
            except OSError as e:
                errors.append(f"{sz}px: {e}")

        if errors:
            self.report({"WARNING"}, "Errors: " + "; ".join(errors))
        if not saved:
            return {"CANCELLED"}

        size_str = ", ".join(f"{s}×{s}" for s in saved)
        self.report({"INFO"}, f"Saved {len(saved)} file(s): [{size_str}] → {os.path.dirname(base)}")
        return {"FINISHED"}

    def invoke(self, context, event):
        name = "icon"
        for area in context.screen.areas:
            if area.type == "IMAGE_EDITOR":
                img = area.spaces.active.image
                if img:
                    name = os.path.splitext(os.path.basename(img.filepath or img.name))[0] or "icon"
                    break
        self.filepath = name + ".ico"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class RENDER_PT_ico_export(Panel):
    bl_label       = "ICO Export"
    bl_idname      = "RENDER_PT_ico_export"
    bl_space_type  = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context     = "output"
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.ico_export_props

        layout.prop(props, "Source")
        layout.label(text="Sizes:")
        col = layout.column(align=True)
        for attr in ("size_16", "size_24", "size_32", "size_48",
                     "size_64", "size_128", "size_256"):
            col.prop(props, attr)

        layout.separator()
        op = layout.operator("image.export_ico", icon="IMAGE_DATA")
        op.Source = props.Source
        for attr in ("size_16", "size_24", "size_32", "size_48",
                     "size_64", "size_128", "size_256"):
            setattr(op, attr, getattr(props, attr))


def menu_image_editor(self, context):
    self.layout.separator()
    self.layout.operator(
        IMAGE_OT_export_ico.bl_idname,
        text="Export as ICO (.ico)",
        icon="IMAGE_DATA",
    )


def menu_file_export(self, context):
    self.layout.operator(
        IMAGE_OT_export_ico.bl_idname,
        text="ICO (Windows Icon) (.ico)",
        icon="IMAGE_DATA",
    )


def menu_image_save_as(self, context):
    self.layout.separator()
    self.layout.operator(
        IMAGE_OT_export_ico.bl_idname,
        text="Export as ICO (.ico)",
        icon="IMAGE_DATA",
    )


classes = (
    IcoExportProperties,
    IMAGE_OT_export_ico,
    RENDER_PT_ico_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.ico_export_props = bpy.props.PointerProperty(type=IcoExportProperties)

    bpy.types.IMAGE_MT_image.append(menu_image_editor)
    bpy.types.TOPBAR_MT_file_export.append(menu_file_export)

    try:
        bpy.types.IMAGE_MT_image_save_as.append(menu_image_save_as)
    except AttributeError:
        pass


def unregister():
    try:
        bpy.types.IMAGE_MT_image_save_as.remove(menu_image_save_as)
    except AttributeError:
        pass

    bpy.types.TOPBAR_MT_file_export.remove(menu_file_export)
    bpy.types.IMAGE_MT_image.remove(menu_image_editor)

    del bpy.types.Scene.ico_export_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()