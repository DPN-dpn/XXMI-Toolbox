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
        
        # 패널 내부 우측 상단에 툴팁 배치
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = "선택한 소스 메쉬의 XXMI 커스텀 속성(오브젝트/메쉬)을 타겟 메쉬로 덮어씌웁니다"

        layout.use_property_split = True
        layout.use_property_decorate = False
        
        props = context.scene.xxmi_copy_props

        col = layout.column(align=True)
        col.prop(props, "source_obj")
        col.prop(props, "target_obj")
        
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
