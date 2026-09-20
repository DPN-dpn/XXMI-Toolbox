import bpy

class XXMI_TOOLBOX_PT_separate_mesh_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "XXMI_TOOLBOX_PT_separate_mesh_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XXMI Toolbox"
    bl_order = 2
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="버텍스 그룹 기준 메쉬 분리", icon='GROUP_VERTEX')

    def draw(self, context):
        layout = self.layout
        
        # 패널 내부 우측 상단에 툴팁 배치
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = (
            "버텍스 그룹과 엣지 연결성을 분석하여 하나의 메쉬를 여러 파츠로 쪼개고 컬렉션으로 깔끔하게 정리합니다.\n\n"
            "[사용 방법]\n"
            "1. 분리할 대상 오브젝트를 지정합니다.\n"
            "2. 필요한 경우 '메시 강제 분리' 옵션을 켭니다.\n"
            "3. '분리 실행' 버튼을 누릅니다.\n\n"
            "[프로퍼티]\n"
            "- 메시 강제 분리: 메쉬가 연결되어 있더라도 버텍스 그룹만을 기준으로 강제로 분리합니다"
        )

        layout.use_property_split = True
        layout.use_property_decorate = False

        props = context.scene.xxmi_separate_mesh_props
        
        col = layout.column(align=True)
        col.prop(props, "target_obj")
        col.prop(props, "ignore_connectivity")
        
        layout.separator()
        layout.operator("object.xxmi_separate_mesh", text="분리 실행", icon='GROUP_VERTEX')

classes = (
    XXMI_TOOLBOX_PT_separate_mesh_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
