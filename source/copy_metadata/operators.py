import bpy

def copy_custom_properties(target_obj, source_obj):
    print(f"\n[커스텀 속성 복사] '{source_obj.name}' -> '{target_obj.name}'")
    
    target_mesh = target_obj.data
    source_mesh = source_obj.data

    # 기존 타겟 오브젝트의 커스텀 속성 제거 (_RNA_UI 제외)
    for k in list(target_obj.keys()):
        if k != '_RNA_UI':
            del target_obj[k]
            
    # 기존 타겟 메쉬의 커스텀 속성 제거
    for k in list(target_mesh.keys()):
        if k != '_RNA_UI':
            del target_mesh[k]

    # 소스 오브젝트 속성 복사
    for k, v in source_obj.items():
        target_obj[k] = v
        
    # 소스 메쉬 속성 복사
    for k, v in source_mesh.items():
        target_mesh[k] = v

    print(f"  복사 완료!")

class XXMI_OT_copy_props(bpy.types.Operator):
    bl_idname = "object.xxmi_copy_props"
    bl_label = "속성 덮어쓰기"
    bl_description = "소스 오브젝트의 커스텀 속성을 타겟 오브젝트에 복사(덮어쓰기)합니다"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.xxmi_copy_props
        return props.target_obj is not None and props.target_obj.type == 'MESH' and \
               props.source_obj is not None and props.source_obj.type == 'MESH'

    def execute(self, context):
        props = context.scene.xxmi_copy_props

        if not props.target_obj or not props.source_obj:
            self.report({'ERROR'}, "타겟 오브젝트와 소스 오브젝트를 모두 지정해주세요!")
            return {'CANCELLED'}
        if props.target_obj.type != 'MESH' or props.source_obj.type != 'MESH':
            self.report({'ERROR'}, "오브젝트는 반드시 Mesh 타입이어야 합니다.")
            return {'CANCELLED'}

        copy_custom_properties(props.target_obj, props.source_obj)
        self.report({'INFO'}, "커스텀 속성 복사 완료!")
        return {'FINISHED'}

classes = (
    XXMI_OT_copy_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
