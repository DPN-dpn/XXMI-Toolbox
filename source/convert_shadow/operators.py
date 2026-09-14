import bpy
import bmesh

# ──────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────

MERGE_DISTANCE   = 1e-4    # Merge by Distance 허용 거리
COLOR_LAYER_NAME = "COLOR"

# 버텍스 쉐이더(bcddceab76ee10ce)는 COLOR.R(v2.x) 값에 비례해서
# 그림자 메쉬를 광원 방향으로 밀어낸다. 0이면 오프셋 없이 헤어와 겹침.
# 오프셋 레벨은 UI에서 입력받으며 (레벨 / 255.0) 으로 계산된다.


# ──────────────────────────────────────────────────────────────
# 내부 헬퍼 함수
# ──────────────────────────────────────────────────────────────

def _fix_xxmi_metadata(obj, mesh, shadow_ref):
    """헤어의 XXMI Custom Properties를 shadow_ref 기준으로 교체.

    XXMI Tools는 Custom Properties(fmt, hash 등)를 기반으로
    버텍스 버퍼 포맷을 결정하므로, 그림자 에셋의 포맷 정보를
    그대로 복사해야 올바른 포맷으로 내보내진다.
    """
    # 기존 헤어의 XXMI 속성 제거
    for k in list(obj.keys()):
        if k != '_RNA_UI':
            del obj[k]
    for k in list(mesh.keys()):
        if k != '_RNA_UI':
            del mesh[k]

    # shadow_ref의 XXMI 속성 복사
    for k, v in shadow_ref.items():
        obj[k] = v
    for k, v in shadow_ref.data.items():
        mesh[k] = v

    print(f"  메타데이터: '{shadow_ref.name}' 기준으로 교체 완료")


def _convert_color_attribute(mesh, offset_level):
    """COLOR 어트리뷰트를 그림자 오프셋용 고정값으로 교체.

    기존 레이어 이름을 유지하면서 타입을 FLOAT_COLOR로 재생성하고,
    모든 버텍스에 (offset_level/255.0, 0, 0, 1) 을 균일하게 적용한다.
    """
    use_new_api = hasattr(mesh, "color_attributes")

    # 기존 COLOR 레이어 탐색 (이름 보존 목적)
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

    # 기존 레이어 제거 후 FLOAT_COLOR 타입으로 재생성
    if use_new_api:
        mesh.color_attributes.remove(src_layer)
        new_layer = mesh.color_attributes.new(
            name=layer_name, type="FLOAT_COLOR", domain="CORNER"
        )
    else:
        mesh.vertex_colors.remove(src_layer)
        new_layer = mesh.vertex_colors.new(name=layer_name)

    shadow_r = offset_level / 255.0
    shadow_color = (shadow_r, 0.0, 0.0, 1.0)
    for cd in new_layer.data:
        cd.color = shadow_color

    print(f"  COLOR: '{layer_name}' → R={shadow_r:.5f} 로 {len(new_layer.data)}개 버텍스 적용")


def _clean_uv_layers(mesh, shadow_ref):
    """shadow_ref의 UV 레이어 구성에 맞게 헤어의 UV 레이어를 정리.

    XXMI Tools는 UV 레이어 이름과 순서로 TEXCOORD 슬롯을 결정하므로
    shadow_ref와 동일한 구성이 필요하다.
    'TEXCOORD1' 과 'TEXCOORD1.xy' 는 동등하게 취급한다.
    """
    uv_layers = mesh.uv_layers

    # shadow_ref의 UV 레이어 이름 집합 (원형 + .xy 변형 모두 포함)
    ref_names = {uv.name for uv in shadow_ref.data.uv_layers}
    keep_names = set()
    for name in ref_names:
        keep_names.add(name)
        keep_names.add(name[:-3] if name.endswith(".xy") else name + ".xy")

    print(f"  UV 보존 목록: {sorted(keep_names)}")

    # 보존 목록에 없는 레이어 제거
    for name in [uv.name for uv in uv_layers if uv.name not in keep_names]:
        uv = uv_layers.get(name)
        if uv:
            uv_layers.remove(uv)
            print(f"  UV 제거: '{name}'")

    # shadow_ref에 있는데 메쉬에 없는 레이어 생성
    existing = {uv.name for uv in uv_layers}
    for ref_name in ref_names:
        variants = {ref_name, ref_name + ".xy"} if not ref_name.endswith(".xy") \
                   else {ref_name, ref_name[:-3]}
        if not variants & existing:
            uv_layers.new(name=ref_name)
            print(f"  UV 생성: '{ref_name}'")

    # XXMI 호환: TEXCOORD1.xy 가 있으면 TEXCOORD.xy 도 필요
    existing = {uv.name for uv in uv_layers}
    has_tc1 = bool({"TEXCOORD1", "TEXCOORD1.xy"} & existing)
    has_tc0 = bool({"TEXCOORD", "TEXCOORD.xy"} & existing)
    if has_tc1 and not has_tc0:
        uv_layers.new(name="TEXCOORD.xy")
        print("  UV 생성: 'TEXCOORD.xy' (XXMI Tools 호환용)")


# ──────────────────────────────────────────────────────────────
# 메인 변환 함수
# ──────────────────────────────────────────────────────────────

def convert_to_shadow(src_obj, shadow_ref, offset_level):
    """헤어 오브젝트를 XXMI 그림자 오브젝트로 변환.

    변환 순서:
      1. 오브젝트 복제 및 이름 설정
      2. XXMI 메타데이터를 shadow_ref 기준으로 교체
      3. Merge by Distance (중복 버텍스 제거)
      4. COLOR 어트리뷰트를 그림자 오프셋용 값으로 교체
      5. UV 레이어를 shadow_ref 기준으로 정리
    """
    print(f"\n[Shadow 변환 시작] '{src_obj.name}'")

    # 1. 복제
    shadow_obj      = src_obj.copy()
    shadow_obj.data = src_obj.data.copy()
    shadow_obj.name            = src_obj.name      + "_Shadow"
    shadow_obj.data.name       = src_obj.data.name + "_Shadow"
    bpy.context.collection.objects.link(shadow_obj)
    new_mesh = shadow_obj.data

    # 2. XXMI 메타데이터 교체
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


# ──────────────────────────────────────────────────────────────
# Blender Operator
# ──────────────────────────────────────────────────────────────

class XXMI_OT_convert_shadow(bpy.types.Operator):
    bl_idname     = "object.xxmi_convert_shadow"
    bl_label      = "그림자 오브젝트로 변환"
    bl_description = "선택된 Target Hair를 XXMI 그림자 오브젝트로 변환합니다"
    bl_options    = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.xxmi_shadow_props
        return props.target_obj is not None and props.target_obj.type == 'MESH'

    def execute(self, context):
        props = context.scene.xxmi_shadow_props

        if not props.shadow_ref:
            self.report({'ERROR'}, "Shadow Reference를 지정해주세요!")
            return {'CANCELLED'}
        if props.shadow_ref.type != 'MESH':
            self.report({'ERROR'}, "Shadow Reference는 Mesh 오브젝트여야 합니다.")
            return {'CANCELLED'}

        convert_to_shadow(props.target_obj, props.shadow_ref, props.shadow_offset_layer)
        self.report({'INFO'}, "Shadow 변환 완료!")
        return {'FINISHED'}


classes = (XXMI_OT_convert_shadow,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
