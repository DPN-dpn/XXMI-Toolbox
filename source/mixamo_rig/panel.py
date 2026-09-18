import bpy

class XXMI_TOOLBOX_PT_mixamo_rig_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "XXMI_TOOLBOX_PT_mixamo_rig_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="Mixamo 리깅 변환", icon='ARMATURE_DATA')

    def draw(self, context):
        layout = self.layout
        
        # 패널 내부 우측 상단에 툴팁 배치
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = "선택한 Armature의 본 이름에서 mixamorig: 접두사를 제거하고, Left/Right를 블렌더 표준인 .L/.R 접미사로 변환합니다."

        layout.use_property_split = True
        layout.use_property_decorate = False

        props = context.scene.xxmi_mixamo_rig_props
        
        col = layout.column(align=True)
        col.prop(props, "target_obj")
            
        layout.separator()
        layout.operator("object.xxmi_convert_mixamo_rig", text="본 이름 변환", icon='GROUP_BONE')

classes = (
    XXMI_TOOLBOX_PT_mixamo_rig_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
