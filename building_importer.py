bl_info = {
    "name": "DrawBuild For Blender",
    "author": "Sergey Karasev",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tool",
    "description": "Creates 3D models of rooms from JSON with a plan. GitHub: https://github.com/KARASEVV/DrawBuildForBlender.git",
    "warning": "",
    "category": "Import",
}

import bpy
import json
from mathutils import Vector
from bpy.props import (StringProperty, FloatProperty,
                       BoolProperty, PointerProperty)
from bpy_extras.io_utils import ImportHelper
from collections import defaultdict


class WallImporterProperties(bpy.types.PropertyGroup):
    wall_height: FloatProperty(
        name="Wall Height",
        default=3.0,
        min=0.1,
        soft_max=10.0
    )
    wall_thickness: FloatProperty(
        name="Wall Thickness",
        default=0.2,
        min=0.01,
        soft_max=1.0
    )
    door_height: FloatProperty(
        name="Door Height",
        default=2.1,
        min=0.5,
        max=3.0,
        description="Height from floor to top of door"
    )
    window_bottom: FloatProperty(
        name="Window Bottom",
        default=0.9,
        min=0.0,
        max=3.0,
        description="Height from floor to window bottom"
    )
    window_top: FloatProperty(
        name="Window Top",
        default=1.5,
        min=0.1,
        max=3.0,
        description="Height from floor to window top"
    )
    scale_factor: FloatProperty(
        name="Scale",
        default=0.01,
        min=0.0001,
        max=1.0
    )
    texture_scale_x: FloatProperty(
        name="Texture Scale X",
        default=1.0,
        min=0.01,
        max=10.0
    )
    texture_scale_y: FloatProperty(
        name="Texture Scale Y",
        default=1.0,
        min=0.01,
        max=10.0
    )
    corner_overlap: FloatProperty(
        name="Corner Overlap",
        default=0.05,
        min=0.0,
        max=0.2,
        description="Overlap amount at corners"
    )
    floor_thickness: FloatProperty(
        name="Floor Thickness",
        default=0.0,
        min=0.0,
        max=1.0
    )
    create_floor: BoolProperty(
        name="Create Floor",
        default=True
    )


class IMPORT_OT_walls(bpy.types.Operator, ImportHelper):
    bl_idname = "import.walls"
    bl_label = "Import JSON"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        props = context.scene.wall_importer_props

        # Clear scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"JSON Error: {e}")
            return {'CANCELLED'}

        # Collect all points for floor calculation
        all_points = []
        connection_map = defaultdict(list)
        processed_segments = set()

        # First pass: collect all elements and connections
        elements = []
        for elem in data.get('elements', []):
            if elem.get('type') in ['wall', 'door', 'window']:
                try:
                    start = (round(elem['start']['x'], 4), round(elem['start']['y'], 4))
                    end = (round(elem['end']['x'], 4), round(elem['end']['y'], 4))
                    segment_key = tuple(sorted((start, end)))

                    if segment_key not in processed_segments:
                        processed_segments.add(segment_key)
                        elements.append(elem)
                        connection_map[start].append(end)
                        connection_map[end].append(start)
                        all_points.extend([start, end])
                except KeyError:
                    continue

        # Create floor if needed
        if all_points and props.create_floor:
            x_coords = [p[0] for p in all_points]
            y_coords = [p[1] for p in all_points]
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)

            self.create_floor(
                min_x * props.scale_factor,
                max_x * props.scale_factor,
                min_y * props.scale_factor,
                max_y * props.scale_factor,
                props.floor_thickness,
                props.texture_scale_x,
                props.texture_scale_y
            )

        # Second pass: create walls, doors and windows
        wall_count = 0
        door_count = 0
        window_count = 0

        for elem in elements:
            try:
                start = (round(elem['start']['x'], 4), round(elem['start']['y'], 4))
                end = (round(elem['end']['x'], 4), round(elem['end']['y'], 4))

                start_pos = (start[0] * props.scale_factor, start[1] * props.scale_factor)
                end_pos = (end[0] * props.scale_factor, end[1] * props.scale_factor)

                # Determine if we need to extend ends
                extend_start = len(connection_map[start]) > 1
                extend_end = len(connection_map[end]) > 1

                if elem.get('type') == 'wall':
                    self.create_wall_segment(
                        start_pos, end_pos,
                        0,  # From floor
                        props.wall_height,  # To ceiling
                        props.wall_thickness,
                        props.texture_scale_x,
                        props.texture_scale_y,
                        props.corner_overlap,
                        extend_start,
                        extend_end,
                        "Wall"
                    )
                    wall_count += 1
                elif elem.get('type') == 'door':
                    # Create bottom part (from floor to door height)
                    self.create_wall_segment(
                        start_pos, end_pos,
                        0,  # From floor
                        props.door_height,  # To door height
                        props.wall_thickness,
                        props.texture_scale_x,
                        props.texture_scale_y,
                        props.corner_overlap,
                        extend_start,
                        extend_end,
                        "DoorBottom"
                    )

                    # Create top lintel (from door height to wall height)
                    if props.door_height < props.wall_height:
                        self.create_wall_segment(
                            start_pos, end_pos,
                            props.door_height,  # From door height
                            props.wall_height,  # To ceiling
                            props.wall_thickness,
                            props.texture_scale_x,
                            props.texture_scale_y,
                            props.corner_overlap,
                            extend_start,
                            extend_end,
                            "DoorLintel"
                        )
                    door_count += 1
                elif elem.get('type') == 'window':
                    # Create bottom part (from floor to window bottom)
                    if props.window_bottom > 0:
                        self.create_wall_segment(
                            start_pos, end_pos,
                            0,  # From floor
                            props.window_bottom,  # To window bottom
                            props.wall_thickness,
                            props.texture_scale_x,
                            props.texture_scale_y,
                            props.corner_overlap,
                            extend_start,
                            extend_end,
                            "WindowBottom"
                        )

                    # Create top lintel (from window top to wall height)
                    if props.window_top < props.wall_height:
                        self.create_wall_segment(
                            start_pos, end_pos,
                            props.window_top,  # From window top
                            props.wall_height,  # To ceiling
                            props.wall_thickness,
                            props.texture_scale_x,
                            props.texture_scale_y,
                            props.corner_overlap,
                            extend_start,
                            extend_end,
                            "WindowLintel"
                        )
                    window_count += 1

            except KeyError as e:
                print(f"Skipping element due to error: {e}")
                continue

        self.report({'INFO'}, f"Created {wall_count} walls, {door_count} doors, {window_count} windows and floor")
        return {'FINISHED'}

    def create_wall_segment(self, start, end, bottom_height, top_height, thickness, tex_scale_x, tex_scale_y, overlap,
                            extend_start, extend_end, name):
        """Creates a wall segment between two heights"""
        vec = Vector((end[0] - start[0], end[1] - start[1], 0))
        length = vec.length
        vec.normalize()
        perp = Vector((-vec.y, vec.x, 0)) * thickness / 2

        # Calculate extensions
        start_extension = vec * overlap if extend_start else Vector((0, 0, 0))
        end_extension = -vec * overlap if extend_end else Vector((0, 0, 0))

        # Vertices
        verts = [
            # Bottom vertices
            (start[0] - perp.x - start_extension.x, start[1] - perp.y - start_extension.y, bottom_height),
            (start[0] + perp.x - start_extension.x, start[1] + perp.y - start_extension.y, bottom_height),
            (end[0] + perp.x - end_extension.x, end[1] + perp.y - end_extension.y, bottom_height),
            (end[0] - perp.x - end_extension.x, end[1] - perp.y - end_extension.y, bottom_height),
            # Top vertices
            (start[0] - perp.x - start_extension.x, start[1] - perp.y - start_extension.y, top_height),
            (start[0] + perp.x - start_extension.x, start[1] + perp.y - start_extension.y, top_height),
            (end[0] + perp.x - end_extension.x, end[1] + perp.y - end_extension.y, top_height),
            (end[0] - perp.x - end_extension.x, end[1] - perp.y - end_extension.y, top_height)
        ]

        # Faces
        faces = [
            (0, 1, 2, 3),  # Bottom
            (4, 5, 6, 7),  # Top
            (0, 1, 5, 4),  # Side 1
            (1, 2, 6, 5),  # Side 2
            (2, 3, 7, 6),  # Side 3
            (3, 0, 4, 7)  # Side 4
        ]

        # Create mesh
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        mesh.from_pydata(verts, [], faces)

        # Create UV layer
        uv_layer = mesh.uv_layers.new().data

        # Calculate UV mapping
        segment_height = top_height - bottom_height
        for poly in mesh.polygons:
            if poly.index == 0:  # Bottom face
                for i, loop_idx in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                    u = [0, 1, 1, 0][i]
                    v = [0, 0, 1, 1][i]
                    uv_layer[loop_idx].uv = (u * (length + overlap * 2) / tex_scale_x, v * thickness / tex_scale_y)
            elif poly.index == 1:  # Top face
                for i, loop_idx in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                    u = [0, 1, 1, 0][i]
                    v = [0, 0, 1, 1][i]
                    uv_layer[loop_idx].uv = (u * (length + overlap * 2) / tex_scale_x, v * thickness / tex_scale_y)
            else:  # Side faces
                for i, loop_idx in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                    u = [0, 1, 1, 0][i]
                    v = [0, 0, 1, 1][i]
                    uv_layer[loop_idx].uv = (u * (length + overlap * 2) / tex_scale_x, v * segment_height / tex_scale_y)

        mesh.update()

        # Create object
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)

        # Assign material
        self.create_wall_material(obj, length + overlap * 2, segment_height, tex_scale_x, tex_scale_y)

    def create_floor(self, min_x, max_x, min_y, max_y, thickness, tex_scale_x, tex_scale_y):
        """Creates flat floor (only top face)"""
        # Vertices (only top face)
        verts = [
            (min_x, min_y, 0),  # 0
            (max_x, min_y, 0),  # 1
            (max_x, max_y, 0),  # 2
            (min_x, max_y, 0)  # 3
        ]

        # Faces (only top face)
        faces = [
            (0, 1, 2, 3)  # Top
        ]

        # Create mesh
        mesh = bpy.data.meshes.new("FloorMesh")
        mesh.from_pydata(verts, [], faces)

        # Create UV layer
        uv_layer = mesh.uv_layers.new().data

        # Calculate UVs for floor
        floor_width = max_x - min_x
        floor_depth = max_y - min_y

        for poly in mesh.polygons:
            for i, loop_idx in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                u = [0, 1, 1, 0][i]
                v = [0, 0, 1, 1][i]
                uv_layer[loop_idx].uv = (u * floor_width / tex_scale_x, v * floor_depth / tex_scale_y)

        mesh.update()

        # Create object
        obj = bpy.data.objects.new("Floor", mesh)
        bpy.context.collection.objects.link(obj)

        # Assign material
        self.create_floor_material(obj, floor_width, floor_depth, tex_scale_x, tex_scale_y)

    def create_wall_material(self, obj, length, height, tex_scale_x, tex_scale_y):
        """Creates material for walls with correct texture scaling"""
        mat = bpy.data.materials.new(name="WallMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Clear default nodes
        nodes.clear()

        # Create nodes
        tex_coord = nodes.new('ShaderNodeTexCoord')
        mapping = nodes.new('ShaderNodeMapping')
        image_tex = nodes.new('ShaderNodeTexImage')
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')

        # Setup mapping node
        mapping.inputs['Scale'].default_value = (1 / tex_scale_x, 1 / tex_scale_y, 1)

        # Connect nodes
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], image_tex.inputs['Vector'])
        links.new(image_tex.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # Assign material
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

    def create_floor_material(self, obj, width, depth, tex_scale_x, tex_scale_y):
        """Creates material for floor with correct texture scaling"""
        mat = bpy.data.materials.new(name="FloorMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Clear default nodes
        nodes.clear()

        # Create nodes
        tex_coord = nodes.new('ShaderNodeTexCoord')
        mapping = nodes.new('ShaderNodeMapping')
        image_tex = nodes.new('ShaderNodeTexImage')
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')

        # Setup mapping node
        mapping.inputs['Scale'].default_value = (1 / tex_scale_x, 1 / tex_scale_y, 1)

        # Connect nodes
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], image_tex.inputs['Vector'])
        links.new(image_tex.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # Assign material
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)


class IMPORT_PT_walls_panel(bpy.types.Panel):
    bl_label = "DrawBuild"
    bl_idname = "IMPORT_PT_walls"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        props = context.scene.wall_importer_props

        # Wall settings
        box = layout.box()
        box.label(text="Wall Settings")
        box.prop(props, "wall_height")
        box.prop(props, "wall_thickness")
        box.prop(props, "door_height")
        box.prop(props, "window_bottom")
        box.prop(props, "window_top")
        box.prop(props, "corner_overlap")

        # Floor settings
        box = layout.box()
        box.label(text="Floor Settings")
        box.prop(props, "create_floor")
        if props.create_floor:
            box.prop(props, "floor_thickness")

        # Texture settings
        box = layout.box()
        box.label(text="Texture Settings")
        row = box.row()
        row.prop(props, "texture_scale_x")
        row.prop(props, "texture_scale_y")

        # General settings
        box = layout.box()
        box.label(text="General Settings")
        box.prop(props, "scale_factor")

        layout.operator("import.walls")


def register():
    bpy.utils.register_class(WallImporterProperties)
    bpy.utils.register_class(IMPORT_OT_walls)
    bpy.utils.register_class(IMPORT_PT_walls_panel)
    bpy.types.Scene.wall_importer_props = PointerProperty(type=WallImporterProperties)


def unregister():
    bpy.utils.unregister_class(WallImporterProperties)
    bpy.utils.unregister_class(IMPORT_OT_walls)
    bpy.utils.unregister_class(IMPORT_PT_walls_panel)
    del bpy.types.Scene.wall_importer_props


if __name__ == "__main__":
    register()