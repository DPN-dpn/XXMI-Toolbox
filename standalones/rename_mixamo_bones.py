import bpy

# ==============================================================================
# [ 사용 방법 ]
# 1. 3D 뷰포트에서 '변환할 Armature(뼈대)'를 클릭하여 활성화(Active) 합니다.
# 2. 이 스크립트를 실행(Run) 합니다.
# ==============================================================================

def main():
    # 현재 선택된 오브젝트 확인
    obj = bpy.context.active_object

    def show_error(message):
        print(f"ERROR: {message}")
        def draw(self, context):
            self.layout.label(text=message)
        bpy.context.window_manager.popup_menu(draw, title="오류", icon='ERROR')

    if not obj or obj.type != 'ARMATURE':
        show_error("Armature(뼈) 오브젝트를 먼저 선택해 주세요.")
        return

    # 에디트 모드나 포즈 모드일 경우 오브젝트 모드로 전환해 적용
    if bpy.context.mode != 'OBJECT':
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

    print(f"Mixamo 본 이름 {changed_count}개 변환 완료!")
    def draw(self, context):
        self.layout.label(text=f"Mixamo 본 이름 {changed_count}개 변환 완료!")
    bpy.context.window_manager.popup_menu(draw, title="성공", icon='INFO')

if __name__ == "__main__":
    main()
