import bpy
import bmesh

MERGE_DISTANCE = 1e-4
COLOR_LAYER_NAME = "COLOR"
SHADOW_LAYER3_COLOR = (3 / 255.0, 0.0, 0.0, 1.0)

def _fix_xxmi_metadata(obj, mesh, shadow_ref):
    """메인 헤어의 메타데이터를 지우고, 그림자 모델의 메타데이터로 교체"""
    # 1. 기존 속성 초기화 (메인 헤어의 fmt 정보 삭제)
    for k in list(obj.keys()):
        if k not in ['_RNA_UI']: del obj[k]
    for k in list(mesh.keys()):
        if k not in ['_RNA_UI']: del mesh[k]

    # 2. 패널에서 지정한 원본 그림자 에셋의 메타데이터 복사
    print(f"  XXMI 원본 그림자 참조: '{shadow_ref.name}' -> 메타데이터 복사 완료")
    for k, v in shadow_ref.items():
        obj[k] = v
    for k, v in shadow_ref.data.items():
        mesh[k] = v

def _convert_color_attribute(mesh):
    """COLOR 어트리뷰트를 레이어 3(오프셋 값)으로 고정하여 변환"""
    use_new_api = hasattr(mesh, "color_attributes")
    src_layer = None

    if use_new_api:
        attrs = mesh.color_attributes
        if COLOR_LAYER_NAME in attrs: src_layer = attrs[COLOR_LAYER_NAME]
        elif attrs: src_layer = attrs[0]
    else:
        vc = mesh.vertex_colors
        if COLOR_LAYER_NAME in vc: src_layer = vc[COLOR_LAYER_NAME]
        elif vc: src_layer = vc.active

    if src_layer is None: return

    old_name = src_layer.name
    if use_new_api:
        mesh.color_attributes.remove(src_layer)
        new_layer = mesh.color_attributes.new(name=old_name, type="FLOAT_COLOR", domain="CORNER")
    else:
        mesh.vertex_colors.remove(src_layer)
        new_layer = mesh.vertex_colors.new(name=old_name)

    for cd in new_layer.data:
        cd.color = SHADOW_LAYER3_COLOR

def _clean_uv_layers(mesh, shadow_ref):
    """원본 그림자 에셋의 UV 레이어 구성을 기준으로 정리"""
    uv_layers = mesh.uv_layers

    # 1. shadow_ref의 실제 UV 레이어 이름을 기준으로 보존 목록 결정
    ref_uv_names = {uv.name for uv in shadow_ref.data.uv_layers}
    # XXMI는 .xy 접미사 변형도 동일하게 취급하므로 양쪽 형태 모두 허용
    names_to_keep = set()
    for name in ref_uv_names:
        names_to_keep.add(name)
        # 'TEXCOORD' <-> 'TEXCOORD.xy' 쌍 자동 추가
        if name.endswith(".xy"):
            names_to_keep.add(name[:-3])
        else:
            names_to_keep.add(name + ".xy")

    print(f"  UV 보존 목록 (shadow_ref 기준): {sorted(names_to_keep)}")

    # 2. 보존 목록에 없는 레이어 삭제
    for name in [uv.name for uv in uv_layers if uv.name not in names_to_keep]:
        uv = uv_layers.get(name)
        if uv is not None:
            print(f"  UV 레이어 제거: '{name}'")
            uv_layers.remove(uv)

    # 3. shadow_ref에 있는 UV 레이어가 없으면 새로 생성
    for ref_name in ref_uv_names:
        if not any(uv.name in (ref_name, ref_name + ".xy", ref_name[:-3] if ref_name.endswith(".xy") else ref_name) for uv in uv_layers):
            uv_layers.new(name=ref_name)
            print(f"  UV 레이어 생성: '{ref_name}' (shadow_ref 기준)")

    # 4. XXMI Tools 고질병 대응: TEXCOORD1.xy가 있으면 TEXCOORD.xy도 반드시 있어야 함
    #    없으면 빈 UV맵을 만들어 이름만 맞춰둠
    has_texcoord1 = any(uv.name in ("TEXCOORD1", "TEXCOORD1.xy") for uv in uv_layers)
    has_texcoord0 = any(uv.name in ("TEXCOORD", "TEXCOORD.xy") for uv in uv_layers)
    if has_texcoord1 and not has_texcoord0:
        uv_layers.new(name="TEXCOORD.xy")
        print(f"  UV 레이어 생성: 'TEXCOORD.xy' (XXMI Tools 호환용 빈 UV)")


def convert_to_shadow(src_obj, shadow_ref):
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

    # ── 4. COLOR 어트리뷰트 변환 (헤어 Alpha → 그림자 레이어) ───────────
    _convert_color_attribute(new_mesh)

    # ── 5. UV 레이어 정리 (shadow_ref 기준) ──────────────────────
    _clean_uv_layers(new_mesh, shadow_ref)

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
        if not props.shadow_ref:
            self.report({'ERROR'}, "Shadow Reference를 지정해주세요! (원본 그림자 에셋 오브젝트 필요)")
            return {'CANCELLED'}
        if props.shadow_ref.type != 'MESH':
            self.report({'ERROR'}, "Shadow Reference는 Mesh 오브젝트여야 합니다.")
            return {'CANCELLED'}
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
