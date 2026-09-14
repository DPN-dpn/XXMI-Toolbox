import bpy

class XXMI_PG_copy_props(bpy.types.PropertyGroup):
    target_obj: bpy.props.PointerProperty(
        name="타겟",
        type=bpy.types.Object,
        description="커스텀 속성을 덮어씌울 오브젝트"
    )
    source_obj: bpy.props.PointerProperty(
        name="소스",
        type=bpy.types.Object,
        description="커스텀 속성을 복사해 올 원본 오브젝트"
    )

classes = (
    XXMI_PG_copy_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xxmi_copy_props = bpy.props.PointerProperty(type=XXMI_PG_copy_props)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.xxmi_copy_props
