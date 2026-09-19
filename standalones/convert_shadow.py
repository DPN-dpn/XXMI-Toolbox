import bpy
import bmesh

# ==============================================================================
# [ 사용 방법 ]
# 1. 3D 뷰포트에서 그림자로 변환할 메쉬 하나만 선택합니다.
# 2. 이 스크립트를 실행(Run) 합니다.
# ==============================================================================

# ==============================================================================
# [ 설정 ]
# ==============================================================================
# 그림자를 밀어내는 정도 (0: 밀어내지 않음, 값이 클수록 멀어짐, 권장: 3)
SHADOW_OFFSET_LEVEL = 3

# ==============================================================================
# [ 상수 ]
# ==============================================================================
# Merge by Distance 허용 거리
MERGE_DISTANCE = 1e-4

COLOR_LAYER_NAME = "COLOR"

SHADOW_TEMPLATE = {
    "object_properties": {
        "3DMigoto:VBLayout": [
            {
                "SemanticName": "POSITION",
                "SemanticIndex": 0,
                "Format": "R32G32B32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 0,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "NORMAL",
                "SemanticIndex": 0,
                "Format": "R32G32B32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 12,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "TANGENT",
                "SemanticIndex": 0,
                "Format": "R32G32B32A32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 24,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "BLENDWEIGHTS",
                "SemanticIndex": 0,
                "Format": "R32G32B32A32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 40,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "BLENDINDICES",
                "SemanticIndex": 0,
                "Format": "R32G32B32A32_UINT",
                "InputSlot": 0,
                "AlignedByteOffset": 56,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "COLOR",
                "SemanticIndex": 0,
                "Format": "R32G32B32A32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 72,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            },
            {
                "SemanticName": "TEXCOORD",
                "SemanticIndex": 1,
                "Format": "R32G32_FLOAT",
                "InputSlot": 0,
                "AlignedByteOffset": 88,
                "InputSlotClass": "per-vertex",
                "InstanceDataStepRate": 0
            }
        ],
        "3DMigoto:Topology": "trianglelist",
        "3DMigoto:VB0Stride": 96,
        "3DMigoto:FirstVertex": 0,
        "3DMigoto:FlipWinding": False,
        "3DMigoto:FlipNormal": False,
        "3DMigoto:FlipMesh": False,
        "3DMigoto:IBFormat": "DXGI_FORMAT_R16_UINT",
        "3DMigoto:FirstIndex": 0,
        "3DMigoto:TEXCOORD1.xy": {
            "flip_v": True
        }
    },
    "mesh_properties": {},
    "uv_layers": [
        "TEXCOORD1.xy"
    ]
}

# ==============================================================================
# [ 로직 ]
# ==============================================================================

def _apply_shadow_template(obj, mesh):
    for k in list(obj.keys()):
        if k != '_RNA_UI': del obj[k]
    for k in list(mesh.keys()):
        if k != '_RNA_UI': del mesh[k]

    for k, v in SHADOW_TEMPLATE["object_properties"].items():
        obj[k] = v
    for k, v in SHADOW_TEMPLATE["mesh_properties"].items():
        mesh[k] = v
    print("  메타데이터: 템플릿 기준으로 교체 완료")

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

def _clean_uv_layers(mesh):
    uv_layers = mesh.uv_layers

    ref_names = set(SHADOW_TEMPLATE["uv_layers"])
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

def convert_to_shadow(src_obj, offset_level):
    print(f"\n[Shadow 변환 시작] '{src_obj.name}'")

    # 1. 복제
    shadow_obj = src_obj.copy()
    shadow_obj.data = src_obj.data.copy()
    shadow_obj.name = src_obj.name + "_Shadow"
    shadow_obj.data.name = src_obj.data.name + "_Shadow"
    bpy.context.collection.objects.link(shadow_obj)
    new_mesh = shadow_obj.data

    # 2. 메타데이터 교체
    _apply_shadow_template(shadow_obj, new_mesh)

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
    _clean_uv_layers(new_mesh)

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

    if len(selected) != 1:
        show_error("그림자로 변환할 메쉬 오브젝트 1개만 선택해주세요.")
        return

    if not target_obj or target_obj.type != 'MESH':
        show_error("메쉬가 선택되지 않았거나 메쉬가 아닙니다.")
        return

    convert_to_shadow(target_obj, SHADOW_OFFSET_LEVEL)

    # 작업 완료 후 새로 생성된 그림자 오브젝트 선택
    bpy.ops.object.select_all(action='DESELECT')
    new_shadow = bpy.context.scene.objects.get(target_obj.name + "_Shadow")
    if new_shadow:
        new_shadow.select_set(True)
        bpy.context.view_layer.objects.active = new_shadow

if __name__ == "__main__":
    main()
