import bpy
import bmesh

# ==============================================================================
# [ 사용 방법 ]
# 1. 3D 뷰포트에서 '원본 그림자 에셋'을 먼저 클릭합니다. (메타데이터 추출용)
# 2. Ctrl 키를 누른 상태로 '그림자로 변환할 메쉬'를 클릭하여 추가 선택합니다.
#    (이때 마지막에 선택한 타겟 메쉬가 노란색 윤곽선의 활성 오브젝트가 되어야 합니다)
# 3. 이 스크립트를 실행(Run) 합니다.
# ==============================================================================

# ==============================================================================
# [ 설정 ]
# ==============================================================================
# 그림자를 밀어내는 정도 (0: 밀어내지 않음, 값이 클수록 멀어짐, 권장: 3)
SHADOW_OFFSET_LEVEL = 3

# Merge by Distance 허용 거리
MERGE_DISTANCE = 1e-4

COLOR_LAYER_NAME = "COLOR"

# ==============================================================================
# [ 로직 ]
# ==============================================================================

def _fix_xxmi_metadata(obj, mesh, shadow_ref):
    for k in list(obj.keys()):
        if k != '_RNA_UI': del obj[k]
    for k in list(mesh.keys()):
        if k != '_RNA_UI': del mesh[k]

    for k, v in shadow_ref.items():
        obj[k] = v
    for k, v in shadow_ref.data.items():
        mesh[k] = v
    print(f"  메타데이터: '{shadow_ref.name}' 기준으로 교체 완료")

def _convert_color_attribute(mesh, offset_level):
    use_new_api = hasattr(mesh, "color_attributes")

    if use_new_api:
        attrs = mesh.color_attributes
        src_layer = attrs.get(COLOR_LAYER_NAME) or (attrs[0] if attrs else None)
    else:
        vc = mesh.vertex_colors
        src_layer = vc.get(COLOR_LAYER_NAME) or vc.active

    if src_layer is None:
        print("  [경고] COLOR 어트리뷰트 없음, 건너뜀")
        return

    layer_name = src_layer.name

    if use_new_api:
        mesh.color_attributes.remove(src_layer)
        new_layer = mesh.color_attributes.new(name=layer_name, type="FLOAT_COLOR", domain="CORNER")
    else:
        mesh.vertex_colors.remove(src_layer)
        new_layer = mesh.vertex_colors.new(name=layer_name)

    shadow_r = offset_level / 255.0
    shadow_color = (shadow_r, 0.0, 0.0, 1.0)
    for cd in new_layer.data:
        cd.color = shadow_color
    print(f"  COLOR: '{layer_name}' → R={shadow_r:.5f} 로 {len(new_layer.data)}개 버텍스 적용")

def _clean_uv_layers(mesh, shadow_ref):
    uv_layers = mesh.uv_layers

    ref_names = {uv.name for uv in shadow_ref.data.uv_layers}
    keep_names = set()
    for name in ref_names:
        keep_names.add(name)
        keep_names.add(name[:-3] if name.endswith(".xy") else name + ".xy")

    for name in [uv.name for uv in uv_layers if uv.name not in keep_names]:
        uv = uv_layers.get(name)
        if uv:
            uv_layers.remove(uv)
            print(f"  UV 제거: '{name}'")

    existing = {uv.name for uv in uv_layers}
    for ref_name in ref_names:
        variants = {ref_name, ref_name + ".xy"} if not ref_name.endswith(".xy") else {ref_name, ref_name[:-3]}
        if not variants & existing:
            uv_layers.new(name=ref_name)
            print(f"  UV 생성: '{ref_name}'")

    existing = {uv.name for uv in uv_layers}
    has_tc1 = bool({"TEXCOORD1", "TEXCOORD1.xy"} & existing)
    has_tc0 = bool({"TEXCOORD", "TEXCOORD.xy"} & existing)
    if has_tc1 and not has_tc0:
        uv_layers.new(name="TEXCOORD.xy")
        print("  UV 생성: 'TEXCOORD.xy' (XXMI Tools 호환용)")

def convert_to_shadow(src_obj, shadow_ref, offset_level):
    print(f"\n[Shadow 변환 시작] '{src_obj.name}'")

    # 1. 복제
    shadow_obj = src_obj.copy()
    shadow_obj.data = src_obj.data.copy()
    shadow_obj.name = src_obj.name + "_Shadow"
    shadow_obj.data.name = src_obj.data.name + "_Shadow"
    bpy.context.collection.objects.link(shadow_obj)
    new_mesh = shadow_obj.data

    # 2. 메타데이터 교체
    _fix_xxmi_metadata(shadow_obj, new_mesh, shadow_ref)

    # 3. Merge by Distance
    bm = bmesh.new()
    bm.from_mesh(new_mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=MERGE_DISTANCE)
    bm.normal_update()
    bm.to_mesh(new_mesh)
    bm.free()
    new_mesh.shade_smooth()
    new_mesh.calc_normals_split()
    print(f"  Merge by Distance 완료 (거리: {MERGE_DISTANCE})")

    # 4. COLOR 어트리뷰트 변환
    _convert_color_attribute(new_mesh, offset_level)

    # 5. UV 레이어 정리
    _clean_uv_layers(new_mesh, shadow_ref)

    print(f"[Shadow 변환 완료] → '{shadow_obj.name}'\n")
    return shadow_obj

def main():
    selected = bpy.context.selected_objects
    target_obj = bpy.context.active_object

    def show_error(message):
        print(f"ERROR: {message}")
        def draw(self, context):
            self.layout.label(text=message)
        bpy.context.window_manager.popup_menu(draw, title="오류", icon='ERROR')

    if len(selected) != 2:
        show_error("정확히 2개의 오브젝트를 선택해주세요.\n(원본 그림자 에셋 먼저 클릭 -> Ctrl+클릭으로 변환할 메쉬 선택)")
        return

    if not target_obj or target_obj.type != 'MESH':
        show_error("변환할 타겟 메쉬가 활성화(Active)되지 않았습니다.\nCtrl+클릭으로 타겟 메쉬를 마지막에 선택해주세요.")
        return

    shadow_refs = [obj for obj in selected if obj != target_obj]
    if not shadow_refs or shadow_refs[0].type != 'MESH':
        show_error("그림자 에셋(Reference) 오브젝트를 찾을 수 없거나 메쉬가 아닙니다.")
        return

    shadow_ref = shadow_refs[0]

    convert_to_shadow(target_obj, shadow_ref, SHADOW_OFFSET_LEVEL)

    # 작업 완료 후 새로 생성된 그림자 오브젝트 선택
    bpy.ops.object.select_all(action='DESELECT')
    new_shadow = bpy.context.scene.objects.get(target_obj.name + "_Shadow")
    if new_shadow:
        new_shadow.select_set(True)
        bpy.context.view_layer.objects.active = new_shadow

if __name__ == "__main__":
    main()
