import bpy
import bmesh

MERGE_DISTANCE = 1e-4
COLOR_LAYER_NAME = "COLOR"
TEXCOORD1_LAYER_NAME = "TEXCOORD1"
LAYER_THRESHOLDS = [13, 38, 63]

def alpha_to_shadow_r(alpha_float):
    alpha_byte = round(alpha_float * 255)
    layer = sum(1 for t in LAYER_THRESHOLDS if alpha_byte >= t)
    return layer / 255.0

def _fix_xxmi_metadata(obj, mesh, shadow_ref=None):
    """메인 헤어의 메타데이터를 지우고, 그림자 모델의 메타데이터로 교체"""
    # 1. 기존 속성 초기화 (메인 헤어의 fmt 정보 삭제)
    for k in list(obj.keys()):
        if k not in ['_RNA_UI']: del obj[k]
    for k in list(mesh.keys()):
        if k not in ['_RNA_UI']: del mesh[k]

    # 2. 씬 내의 원본 그림자 에셋 탐색 (UI에서 참조를 지정하지 않은 경우)
    if not shadow_ref:
        for o in bpy.data.objects:
            if "Shadow" in o.name and o != obj and len(o.keys()) > 1:
                shadow_ref = o
                break
            
    if shadow_ref:
        print(f"  XXMI 원본 그림자 참조 발견: '{shadow_ref.name}' -> 메타데이터 복사 완료")
        for k, v in shadow_ref.items():
            obj[k] = v
        for k, v in shadow_ref.data.items():
            mesh[k] = v
    else:
        print("  [주의] 씬 내에 원본 그림자 에셋(Shadow)이 없어 빈 메타데이터로 진행합니다.")
        print("  내보내기 시 XXMI가 포맷(fmt)을 물어보면 원본 그림자 fmt를 선택하세요.")

def _convert_color_attribute(mesh):
    src_layer = None
    use_new_api = hasattr(mesh, "color_attributes")

    if use_new_api:
        attrs = mesh.color_attributes
        if COLOR_LAYER_NAME in attrs: src_layer = attrs[COLOR_LAYER_NAME]
        elif attrs: src_layer = attrs[0]
    else:
        vc = mesh.vertex_colors
        if COLOR_LAYER_NAME in vc: src_layer = vc[COLOR_LAYER_NAME]
        elif vc: src_layer = vc.active

    if src_layer is None: return

    color_data = []
    for cd in src_layer.data:
        col = tuple(cd.color)
        alpha_f = col[3] if len(col) >= 4 else 0.0
        shadow_r = alpha_to_shadow_r(alpha_f)
        color_data.append((shadow_r, 0.0, 0.0, 1.0))

    old_name = src_layer.name
    if use_new_api:
        mesh.color_attributes.remove(src_layer)
        new_layer = mesh.color_attributes.new(name=old_name, type="FLOAT_COLOR", domain="CORNER")
    else:
        mesh.vertex_colors.remove(src_layer)
        new_layer = mesh.vertex_colors.new(name=old_name)

    for i, cd in enumerate(new_layer.data):
        cd.color = color_data[i]

def _clean_uv_layers(mesh):
    """그림자 모델에 필요한 TEXCOORD.xy, TEXCOORD1.xy 만 남기고 모두 삭제"""
    uv_layers = mesh.uv_layers
    names_to_keep = ["TEXCOORD", "TEXCOORD.xy", "TEXCOORD1", "TEXCOORD1.xy"]
    
    # 1. TEXCOORD2, TEXCOORD3 등 메인 헤어의 불필요한 UV 제거
    for name in [uv.name for uv in uv_layers if uv.name not in names_to_keep]:
        uv = uv_layers.get(name)
        if uv is not None: uv_layers.remove(uv)

    # 2. 필수 UV(TEXCOORD.xy)가 없으면 강제 생성 (XXMI 에러 방지)
    if not any(name in uv_layers for name in ["TEXCOORD", "TEXCOORD.xy"]):
        uv_layers.new(name="TEXCOORD.xy")
    if not any(name in uv_layers for name in ["TEXCOORD1", "TEXCOORD1.xy"]):
        uv_layers.new(name="TEXCOORD1.xy")

def convert_to_shadow(src_obj, shadow_ref=None):
    print(f"\n[Shadow 변환] '{src_obj.name}'")

    # ── 1. 오브젝트 복제 ──────────────────────────────────────
    shadow_obj = src_obj.copy()
    shadow_obj.data = src_obj.data.copy()
    shadow_obj.name = src_obj.name + "_Shadow"
    shadow_obj.data.name = src_obj.data.name + "_Shadow"
    bpy.context.collection.objects.link(shadow_obj)
    new_mesh = shadow_obj.data

    # ── 2. XXMI 메타데이터(Custom Properties) 교체 ─────────────────
    _fix_xxmi_metadata(shadow_obj, new_mesh, shadow_ref)

    # ── 3. Merge by Distance & Normal ───────────────────────────
    bm = bmesh.new()
    bm.from_mesh(new_mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=MERGE_DISTANCE)
    for face in bm.faces:
        face.smooth = True
    bm.normal_update()
    bm.to_mesh(new_mesh)
    bm.free()
    new_mesh.shade_smooth()
    new_mesh.calc_normals_split()

    # ── 4. COLOR 어트리뷰트 변환 ─────────────────────────────────
    _convert_color_attribute(new_mesh)

    # ── 5. UV 레이어 정리 (XXMI 스트라이드 24 강제 유도) ─────────
    _clean_uv_layers(new_mesh)

    print(f"  완료! -> '{shadow_obj.name}'")
    return shadow_obj

class XXMI_OT_convert_shadow(bpy.types.Operator):
    bl_idname = "object.xxmi_convert_shadow"
    bl_label = "그림자 오브젝트로 변환"
    bl_description = "선택된 Target Hair를 그림자 오브젝트로 변환합니다"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.xxmi_shadow_props
        return props.target_obj is not None and props.target_obj.type == 'MESH'

    def execute(self, context):
        props = context.scene.xxmi_shadow_props
        convert_to_shadow(props.target_obj, props.shadow_ref)
        self.report({'INFO'}, "Shadow Conversion Completed!")
        return {'FINISHED'}

classes = (
    XXMI_OT_convert_shadow,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
