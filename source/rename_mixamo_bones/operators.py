import bpy

class XXMI_OT_rename_mixamo_bones(bpy.types.Operator):
    bl_idname = "object.xxmi_rename_mixamo_bones"
    bl_label = "Mixamo 본 이름 변환"
    bl_description = "Mixamo 리깅 본 이름을 블렌더 표준(.L, .R)으로 변환합니다"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.xxmi_rename_mixamo_bones_props
        return props.target_obj is not None and props.target_obj.type == 'ARMATURE'

    def execute(self, context):
        props = context.scene.xxmi_rename_mixamo_bones_props
        obj = props.target_obj
        
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Armature(뼈) 오브젝트를 먼저 선택해 주세요.")
            return {'CANCELLED'}
        
        # 에디트 모드나 포즈 모드일 경우 오브젝트 모드로 전환해 적용
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        changed_count = 0
        for bone in obj.data.bones:
            name = bone.name
            original_name = name
            
            # 1. mixamorig: 접두사 제거
            if name.startswith("mixamorig:"):
                name = name.replace("mixamorig:", "")
                
            # 2. Left / Right 위치를 접미사 .L / .R로 변경
            if name.startswith("Left"):
                name = name.replace("Left", "", 1) + ".L"
            elif name.startswith("Right"):
                name = name.replace("Right", "", 1) + ".R"
                
            # 3. 변경된 이름 적용
            if name != original_name:
                bone.name = name
                changed_count += 1

        self.report({'INFO'}, f"Mixamo 본 이름 {changed_count}개 변환 완료!")
        return {'FINISHED'}

classes = (
    XXMI_OT_rename_mixamo_bones,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
