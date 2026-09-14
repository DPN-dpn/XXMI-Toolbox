import bpy

class XXMI_PG_shadow_props(bpy.types.PropertyGroup):
    target_obj: bpy.props.PointerProperty(
        name="변환할 오브젝트",
        type=bpy.types.Object,
        description="그림자로 변환할 앞머리 오브젝트"
    )
    shadow_ref: bpy.props.PointerProperty(
        name="그림자 에셋",
        type=bpy.types.Object,
        description="그림자 에셋 오브젝트"
    )
    shadow_offset_layer: bpy.props.IntProperty(
        name="오프셋 레벨",
        default=3,
        min=0,
        max=255,
        description="그림자를 밀어내는 정도 (0: 밀어내지 않음, 값이 클수록 멀어짐, 권장: 3)"
    )

classes = (
    XXMI_PG_shadow_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xxmi_shadow_props = bpy.props.PointerProperty(type=XXMI_PG_shadow_props)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.xxmi_shadow_props
