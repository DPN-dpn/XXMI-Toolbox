import bpy

class XXMI_TOOLBOX_PT_shadow_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "XXMI_TOOLBOX_PT_shadow_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"
    bl_order = 1
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="그림자 변환", icon='SHADING_RENDERED')

    def draw(self, context):
        layout = self.layout
        
        # 패널 내부 우측 상단에 툴팁 배치
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = (
            "타겟 오브젝트를 그림자 오브젝트로 변환합니다.\n\n"
            "[사용 방법]\n"
            "1. 그림자 메쉬로 변환할 타겟 오브젝트를 지정합니다.\n"
            "2. 필요한 경우 그림자 오프셋 수치를 조절합니다.\n"
            "3. '변환 실행' 버튼을 누릅니다.\n\n"
            "[프로퍼티]\n"
            "- 그림자 오프셋: 생성되는 그림자 메쉬가 원본 메쉬에서 얼마나 떨어질지 결정합니다. 그림자 거리를 결정합니다"
        )

        layout.use_property_split = True
        layout.use_property_decorate = False
        
        props = context.scene.xxmi_shadow_props

        col = layout.column(align=True)
        col.prop(props, "target_obj")
        col.separator()
        col.prop(props, "shadow_offset_layer")

        layout.separator()
        layout.operator("object.xxmi_convert_shadow", text="변환 실행", icon='SHADING_RENDERED')

classes = (
    XXMI_TOOLBOX_PT_shadow_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
