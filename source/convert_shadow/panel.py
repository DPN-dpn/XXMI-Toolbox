import bpy

class XXMI_TOOLBOX_PT_shadow_panel(bpy.types.Panel):
    bl_label = "그림자 변환 (Shadow)"
    bl_idname = "XXMI_TOOLBOX_PT_shadow_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"

    def draw(self, context):
        layout = self.layout
        props = context.scene.xxmi_shadow_props

        col = layout.column(align=True)
        col.prop(props, "target_obj")
        col.prop(props, "shadow_ref")
        col.separator()
        col.prop(props, "shadow_offset_layer")

        layout.separator()
        layout.operator("object.xxmi_convert_shadow", text="변환 실행 (Convert)", icon='MOD_SHRINKWRAP')

classes = (
    XXMI_TOOLBOX_PT_shadow_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
