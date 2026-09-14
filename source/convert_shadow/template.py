# 그림자 오브젝트 변환 시 필요한 기본 메타데이터 및 UV 레이어 정보
# 특정 캐릭터의 그림자 에셋(shadow_ref) 오브젝트를 요구하지 않고, 
# 이 템플릿의 정보를 주입하여 XXMI 포맷을 맞춥니다.

# 보존/생성해야 할 UV 레이어 목록
SHADOW_UV_LAYERS = [
    "TEXCOORD1.xy",
    "TEXCOORD.xy"
]

# 오브젝트 커스텀 프로퍼티 (Yanagi Shadow 기준)
SHADOW_OBJECT_PROPS = {
    "component_name": "Shadow",
    "root_vs": "e8425f64cfb887cd",
    "draw_vb": "de0bb6f9",
    "position_vb": "9c8be112",
    "blend_vb": "eb448ade",
    "texcoord_vb": "bb35cc80",
    "ib": "c1628e55",
}

# 메쉬 커스텀 프로퍼티
# XXMI Tools 익스포터가 요구하는 버텍스 포맷(fmt) 정보
SHADOW_MESH_PROPS = {
    "fmt_vb0": "POSITION:R32G32B32_FLOAT, NORMAL:R32G32B32_FLOAT, TANGENT:R32G32B32A32_FLOAT",
    "fmt_vb1": "BLENDWEIGHT:R32G32B32A32_FLOAT, BLENDINDICES:R8G8B8A8_UINT",
    "fmt_vb2": "COLOR:R32G32B32A32_FLOAT, TEXCOORD1:R32G32_FLOAT"
}
