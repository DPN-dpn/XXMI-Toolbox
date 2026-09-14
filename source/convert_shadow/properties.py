import bpy

class XXMI_PG_shadow_props(bpy.types.PropertyGroup):
    target_obj: bpy.props.PointerProperty(
        name="Target Hair",
        type=bpy.types.Object,
        description="그림자로 변환할 앞머리 오브젝트 (Mesh)"
    )
    shadow_ref: bpy.props.PointerProperty(
        name="Shadow Reference",
        type=bpy.types.Object,
        description="메타데이터를 복사할 원본 그림자 에셋 오브젝트"
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
