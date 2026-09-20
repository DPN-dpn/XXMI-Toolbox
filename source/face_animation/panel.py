import bpy

class XXMI_PT_face_animation(bpy.types.Panel):
    bl_label = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XXMI Toolbox'
    bl_order = 4
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="얼굴 표정 연동", icon='USER')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.xxmi_face_anim_props

        # 툴팁 (도움말)
        row = layout.row()
        row.alignment = 'RIGHT'
        op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
        op.text = (
            "얼굴 모드에 표정과 립싱크를 연동합니다.\n\n"
            "[사용 방법]\n"
            "1. 원본 캐릭터의 에셋 hash.json 및 얼굴 컴포넌트를 선택합니다.\n"
            "2. 타겟 모드의 폴더를 선택합니다.\n"
            "3. '표정 연동 실행' 버튼을 누르면 타겟 모드에 쉐이더와 버퍼가 자동으로 적용됩니다.\n\n"
            "[맵핑 옵션]\n"
            "- 맵핑 방식: 타겟 모드가 원본 에셋의 표정을 따라갈 수학적 방식을 결정합니다. 가까운 페이스 보간 추천.\n"
            "- 형태 맞춤: 타겟 모드와 원본 에셋의 조형 차이로 이목구비가 지나치게 어긋날 경우,\n"
            "            원본 에셋을 불러와 이목구비를 타겟 모드에 맞게 변형한 후 지정하여 맵핑 정보로 추가합니다.\n\n"
            "[고급 눈 깜빡임]\n"
            "- 눈을 감은 상태의 메쉬를 추가하여 더 자연스러운 눈 깜빡임을 매핑합니다"
        )

        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        
        row = col.row(align=True)
        row.prop(props, "dump_hash_json", text="에셋 hash.json")
        op = row.operator("object.xxmi_file_picker", text="", icon='FILE_FOLDER')
        op.prop_name = "dump_hash_json"
        op.filter_glob = "*.json"
        
        col.prop(props, "selected_component")
        
        row = col.row(align=True)
        row.prop(props, "target_ini", text="타겟 모드 폴더")
        op = row.operator("object.xxmi_dir_picker", text="", icon='FILE_FOLDER')
        op.prop_name = "target_ini"
        
        layout.separator()
        
        col = layout.column(align=True)
        col.prop(props, "mapping_method")
        col.prop(props, "aligned_orig_base")
        
        layout.separator()
        
        layout.prop(props, "use_custom_blink")
        
        if props.use_custom_blink:
            col = layout.column(align=True)
            
            row = col.row(align=True)
            row.prop(props, "orig_blink_dump_hash_json", text="눈 감은 에셋 hash.json")
            op = row.operator("object.xxmi_file_picker", text="", icon='FILE_FOLDER')
            op.prop_name = "orig_blink_dump_hash_json"
            op.filter_glob = "*.json"
            
            col.prop(props, "blink_selected_component")
            
            row = col.row(align=True)
            row.prop(props, "custom_blink_ini", text="눈 감은 모드 ini")
            op = row.operator("object.xxmi_file_picker", text="", icon='FILE_FOLDER')
            op.prop_name = "custom_blink_ini"
            op.filter_glob = "*.ini"
            
        layout.separator()
        layout.operator("object.xxmi_export_face_animation", text="표정 연동 실행", icon='PLAY')
        layout.operator("object.xxmi_rollback_face_animation", text="연동 롤백", icon='RECOVER_LAST')

classes = (
    XXMI_PT_face_animation,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
