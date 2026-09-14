import bpy

class XXMI_TOOLBOX_PT_copy_props_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "XXMI_TOOLBOX_PT_copy_props_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"
    bl_order = 0
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="커스텀 속성 복사", icon='COPYDOWN')

    def draw(self, context):
        layout = self.layout
        props = context.scene.xxmi_copy_props

        col = layout.column(align=True)
        col.prop(props, "target_obj")
        col.prop(props, "source_obj")
        
        layout.separator()
        layout.operator("object.xxmi_copy_props", text="속성 복사 실행", icon='COPYDOWN')

classes = (
    XXMI_TOOLBOX_PT_copy_props_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
