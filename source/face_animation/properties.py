import bpy
import os
import json

def get_component_items(self, context):
    items = []
    hash_path = self.dump_hash_json
    if hash_path and os.path.isfile(hash_path):
        try:
            with open(hash_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for comp in data:
                    name = comp.get("component_name", "Unknown")
                    items.append((name, name, f"{name} Component"))
        except Exception:
            pass
    if not items:
        items.append(("NONE", "--", ""))
    return items

def get_blink_component_items(self, context):
    items = []
    hash_path = self.orig_blink_dump_hash_json
    if hash_path and os.path.isfile(hash_path):
        try:
            with open(hash_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for comp in data:
                    name = comp.get("component_name", "Unknown")
                    items.append((name, name, f"{name} Component"))
        except Exception:
            pass
    if not items:
        items.append(("NONE", "--", ""))
    return items

class XXMI_PG_face_anim_props(bpy.types.PropertyGroup):
    dump_hash_json: bpy.props.StringProperty(
        name="에셋 hash.json",
        description="에셋 hash.json 파일을 선택하세요",
        subtype='NONE'
    )
    
    selected_component: bpy.props.EnumProperty(
        name="얼굴 컴포넌트",
        description="hash.json에서 감지된 컴포넌트 목록입니다. 얼굴(Face)을 선택하세요",
        items=get_component_items
    )
    
    target_ini: bpy.props.StringProperty(
        name="타겟 모드 ini",
        description="표정 연동을 적용할 타겟 모드의 메인 ini 파일을 선택하세요",
        subtype='NONE'
    )
    
    mapping_method: bpy.props.EnumProperty(
        name="맵핑 방식",
        description="버텍스를 연결할 수학적 방식을 선택합니다",
        items=[
            ('TOPOLOGY', '토폴로지', '동일한 버텍스 인덱스를 1:1로 매칭합니다'),
            ('NEAREST_VERTEX', '가까운 버텍스', '가장 가까운 1개의 점에 100% 매핑합니다'),
            ('NEAREST_FACE_VERTEX', '가까운 페이스 버텍스', '가장 가까운 면의 점 중 하나에 매핑합니다'),
            ('NEAREST_FACE_INTERPOLATED', '가까운 페이스 보간', '가장 가까운 면의 3개 점에 무게중심으로 가중치를 분배합니다'),
            ('PROJECTED_FACE_INTERPOLATED', '투사된 페이스 보간', '법선 방향으로 레이저를 쏴 부딪힌 면을 기준으로 보간합니다'),
        ],
        default='NEAREST_FACE_INTERPOLATED'
    )
    
    aligned_orig_base: bpy.props.PointerProperty(
        name="[선택] 형태 맞춤",
        type=bpy.types.Object,
        description="얼굴 조형이 너무 달라서 맵핑이 엇나갈 경우, 눈코입 위치를 커스텀 얼굴에 맞게 찌그러트린 원본 메쉬 오브젝트를 지정하세요"
    )
    
    use_custom_blink: bpy.props.BoolProperty(
        name="고급 눈 깜빡임",
        default=False,
        description="직접 제작한 눈 감은 메쉬를 추가로 연동합니다"
    )
    
    orig_blink_dump_hash_json: bpy.props.StringProperty(
        name="에셋 눈 감은 hash.json",
        description="눈을 감은 상태의 에셋 hash.json 파일을 선택하세요",
        subtype='NONE'
    )
    
    blink_selected_component: bpy.props.EnumProperty(
        name="얼굴 컴포넌트",
        description="눈 감은 에셋의 컴포넌트 목록입니다. 얼굴(Face)을 선택하세요",
        items=get_blink_component_items
    )
    
    custom_blink_ini: bpy.props.StringProperty(
        name="눈 감은 모드 ini",
        description="직접 제작한 눈 감은 타겟 모드의 ini 파일을 선택하세요",
        subtype='NONE'
    )

classes = (
    XXMI_PG_face_anim_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xxmi_face_anim_props = bpy.props.PointerProperty(type=XXMI_PG_face_anim_props)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.xxmi_face_anim_props
