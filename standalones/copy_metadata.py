import bpy

# ==============================================================================
# [ 사용 방법 ]
# 1. 3D 뷰포트에서 '속성을 복사해 올 원본(소스) 메쉬'를 먼저 클릭합니다.
# 2. Ctrl 키를 누른 상태로 '속성을 덮어씌울 타겟 메쉬'를 클릭하여 추가 선택합니다.
#    (이때 마지막에 선택한 타겟 메쉬가 노란색 윤곽선의 활성 오브젝트가 되어야 합니다)
# 3. 이 스크립트를 실행(Run) 합니다.
# ==============================================================================

def copy_custom_properties(target_obj, source_obj):
    print(f"\n[커스텀 속성 복사 시작] '{source_obj.name}' -> '{target_obj.name}'")
    
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

def main():
    selected = bpy.context.selected_objects
    target_obj = bpy.context.active_object

    def show_error(message):
        print(f"ERROR: {message}")
        def draw(self, context):
            self.layout.label(text=message)
        bpy.context.window_manager.popup_menu(draw, title="오류", icon='ERROR')

    if len(selected) != 2:
        show_error("정확히 2개의 오브젝트를 선택해주세요.\n(원본 소스 오브젝트 먼저 클릭 -> Ctrl+클릭으로 덮어쓸 타겟 오브젝트 선택)")
        return

    if not target_obj or target_obj.type != 'MESH':
        show_error("타겟 오브젝트가 활성화(Active)되지 않았거나 메쉬가 아닙니다.\nCtrl+클릭으로 타겟 메쉬를 마지막에 선택해주세요.")
        return

    source_objs = [obj for obj in selected if obj != target_obj]
    if not source_objs or source_objs[0].type != 'MESH':
        show_error("소스(원본) 오브젝트를 찾을 수 없거나 메쉬가 아닙니다.")
        return

    source_obj = source_objs[0]

    copy_custom_properties(target_obj, source_obj)

if __name__ == "__main__":
    main()
