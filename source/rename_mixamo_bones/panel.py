import bpy

class XXMI_TOOLBOX_PT_rename_mixamo_bones_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "XXMI_TOOLBOX_PT_rename_mixamo_bones_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="Mixamo 본 이름 변환", icon='ARMATURE_DATA')

    def draw(self, context):
        layout = self.layout
        
        # 패널 내부 우측 상단에 툴팁 배치
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = (
            "선택한 Armature의 본 이름들을 블렌더 표준(.L/.R 접미사)으로 변환합니다.\n\n"
            "[사용 방법]\n"
            "1. Mixamo 등에서 가져온 Armature(뼈대) 오브젝트를 타겟으로 지정합니다.\n"
            "2. '본 이름 변환 실행' 버튼을 누릅니다.\n\n"
            "[설명]\n"
            "- 외부 툴 뼈대 이름(예: 'LeftArm')을 블렌더 대칭 구조(예: 'Arm.L')로 일괄 변경합니다.\n"
            "- 블렌더의 기본 기능 등을 올바르게 사용하기 위해 필수적입니다"
        )

        layout.use_property_split = True
        layout.use_property_decorate = False

        props = context.scene.xxmi_rename_mixamo_bones_props
        
        col = layout.column(align=True)
        col.prop(props, "target_obj")
            
        layout.separator()
        layout.operator("object.xxmi_rename_mixamo_bones", text="본 이름 변환 실행", icon='GROUP_BONE')

classes = (
    XXMI_TOOLBOX_PT_rename_mixamo_bones_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
